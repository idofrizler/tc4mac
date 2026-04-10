#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk


@dataclass(frozen=True)
class ZipPaneEntry:
    rel_path: str
    name: str
    is_dir: bool
    size: int = 0
    modified_ts: float | None = None


@dataclass
class PaneState:
    name: str
    container: tk.Frame
    current_path: Path
    path_var: tk.StringVar
    tree: ttk.Treeview
    back_stack: list[Path] = field(default_factory=list)
    forward_stack: list[Path] = field(default_factory=list)
    entries: list[Path | ZipPaneEntry | None] = field(default_factory=list)  # None = ".."
    marks: set[Path] = field(default_factory=set)
    sort_column: str = "name"
    sort_desc: bool = False
    zip_path: Path | None = None
    zip_rel_dir: str = ""


class TwoPaneCommander:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TC Mac Lite")
        self.root.geometry("1260x760")
        self.status_var = tk.StringVar(value="Ready")
        self.filter_var = tk.StringVar(value="")
        self.filter_query = ""
        self.filter_mode = False
        self.terminal_visible = False
        self.copy_move_dialog: tk.Toplevel | None = None
        self.copy_move_name_entry: ttk.Entry | None = None
        self.copy_move_select_mode = "name"
        self.favorites_file = Path.home() / ".tc-mac-lite-favorites.json"
        self.state_file = Path.home() / ".tc-mac-lite-state.json"
        self.favorites: list[str] = []

        left_start, right_start = self._load_last_pane_paths()
        self.active_pane: PaneState | None = None
        self.left: PaneState
        self.right: PaneState
        self.panes: ttk.Panedwindow

        self._build_ui(left_start, right_start)
        self._load_favorites()
        self._bind_keys()
        self._refresh_pane(self.left, keep_selection=False)
        self._refresh_pane(self.right, keep_selection=False)
        self._set_active(self.left)
        self.left.tree.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self, left_start: Path, right_start: Path) -> None:
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill=tk.BOTH, expand=True)

        self.panes = ttk.Panedwindow(top, orient=tk.HORIZONTAL)
        self.panes.pack(fill=tk.BOTH, expand=True)

        left_frame = tk.Frame(self.panes, bd=1, relief=tk.GROOVE, highlightthickness=2)
        right_frame = tk.Frame(self.panes, bd=1, relief=tk.GROOVE, highlightthickness=2)
        self.panes.add(left_frame, weight=1)
        self.panes.add(right_frame, weight=1)
        self.panes.bind("<Double-Button-1>", self._recenter_splitter_if_clicked)

        self.left = self._build_pane("Left", left_frame, left_start)
        self.right = self._build_pane("Right", right_frame, right_start)
        self._build_terminal(self.root)

        self.status_bar = ttk.Frame(self.root, padding=(8, 4))
        self.status_bar.pack(fill=tk.X)
        self.status = ttk.Label(self.status_bar, textvariable=self.status_var, anchor=tk.W)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.filter_label = ttk.Label(self.status_bar, textvariable=self.filter_var, anchor=tk.E, width=36)
        self.filter_label.pack(side=tk.RIGHT)

    def _build_pane(self, name: str, parent: tk.Frame, start_path: Path) -> PaneState:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=6, pady=(6, 0))

        path_var = tk.StringVar(value=str(start_path))
        path_entry = ttk.Entry(toolbar, textvariable=path_var)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 6), padx=6)

        cols = ("name", "size", "ext", "modified")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("name", text="Name")
        tree.heading("size", text="Size")
        tree.heading("ext", text="Ext")
        tree.heading("modified", text="Last Modified")
        tree.column("name", width=320, anchor=tk.W, stretch=True)
        tree.column("size", width=100, anchor=tk.E, stretch=False)
        tree.column("ext", width=80, anchor=tk.W, stretch=False)
        tree.column("modified", width=170, anchor=tk.W, stretch=False)
        tree.tag_configure("marked", foreground="#c62828")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        pane = PaneState(name=name, container=parent, current_path=start_path, path_var=path_var, tree=tree)
        self._update_sort_headings(pane)
        copy_btn = tk.Button(
            toolbar,
            text="⧉",
            width=1,
            height=1,
            font=("TkDefaultFont", 11),
            padx=0,
            pady=0,
            bd=1,
            relief=tk.RAISED,
            command=lambda p=pane: self._copy_pane_path(p),
        )
        refresh_btn = tk.Button(
            toolbar,
            text="⟳",
            width=1,
            height=1,
            font=("TkDefaultFont", 11),
            padx=0,
            pady=0,
            bd=1,
            relief=tk.RAISED,
            command=lambda p=pane: self._refresh_specific_pane(p),
        )
        copy_bg = str(copy_btn.cget("background"))
        refresh_bg = str(refresh_btn.cget("background"))
        hover_bg = "#dbeafe"
        copy_btn.configure(activebackground=hover_bg)
        refresh_btn.configure(activebackground=hover_bg)
        copy_btn.pack(side=tk.RIGHT, padx=(4, 0))
        refresh_btn.pack(side=tk.RIGHT, padx=(4, 0))
        def copy_enter(_event: tk.Event) -> None:
            copy_btn.configure(bg=hover_bg)
            self.status_var.set(f"{name}: copy full path")

        def copy_leave(_event: tk.Event) -> None:
            copy_btn.configure(bg=copy_bg)

        def refresh_enter(_event: tk.Event) -> None:
            refresh_btn.configure(bg=hover_bg)
            self.status_var.set(f"{name}: refresh pane")

        def refresh_leave(_event: tk.Event) -> None:
            refresh_btn.configure(bg=refresh_bg)

        copy_btn.bind("<Enter>", copy_enter)
        copy_btn.bind("<Leave>", copy_leave)
        refresh_btn.bind("<Enter>", refresh_enter)
        refresh_btn.bind("<Leave>", refresh_leave)

        tree.bind("<FocusIn>", lambda _e, p=pane: self._set_active(p))
        tree.bind("<Double-Button-1>", lambda e, p=pane: self._handle_tree_double_click(e, p))
        tree.bind("<Return>", lambda _e, p=pane: self._open_selected(p))
        tree.bind("<space>", lambda _e, p=pane: self._toggle_mark_current(p))
        tree.bind("<Up>", lambda _e: self._move_selection(-1))
        tree.bind("<Down>", lambda _e: self._move_selection(1))
        tree.bind("<BackSpace>", lambda _e, p=pane: self._handle_backspace(p))
        tree.bind("<KeyPress>", lambda e, p=pane: self._handle_keypress(e, p))
        tree.bind("<F5>", lambda _e: self._handle_copy_shortcut())
        tree.bind("<F6>", lambda _e: self._handle_move_shortcut())
        tree.bind("<Right>", self._handle_right_key)
        if name == "Left":
            tree.bind("<Control-Right>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
            tree.bind("<Command-Right>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
        else:
            tree.bind("<Control-Left>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
            tree.bind("<Command-Left>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
        tree.bind("<Escape>", lambda _e: self._clear_filter())
        tree.bind("<Control-r>", self._handle_refresh_shortcut)
        tree.bind("<Control-R>", self._handle_refresh_shortcut)
        tree.bind("<Button-2>", lambda e, p=pane: self._handle_pane_secondary_click(e, p))
        tree.bind("<Button-3>", lambda e, p=pane: self._handle_pane_secondary_click(e, p))
        path_entry.bind("<Return>", lambda _e, n=name: self._go_to_path(n))
        path_entry.bind("<F5>", lambda _e: self._handle_copy_shortcut())
        path_entry.bind("<F6>", lambda _e: self._handle_move_shortcut())
        path_entry.bind("<Control-r>", self._handle_refresh_shortcut)
        path_entry.bind("<Control-R>", self._handle_refresh_shortcut)
        if name == "Left":
            path_entry.bind("<Control-Right>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
            path_entry.bind("<Command-Right>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
        else:
            path_entry.bind("<Control-Left>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))
            path_entry.bind("<Command-Left>", lambda _e, p=pane: self._open_selected_dir_in_other_pane(p))

        return pane

    def _copy_pane_path(self, pane: PaneState) -> None:
        value = pane.path_var.get().strip()
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.status_var.set(f"{pane.name} path copied")

    def _refresh_specific_pane(self, pane: PaneState) -> None:
        self._refresh_pane(pane, keep_selection=True)
        self.status_var.set(f"Refreshed: {self._zip_display_path(pane)}")

    def _build_terminal(self, parent: tk.Widget) -> None:
        self.terminal_frame = ttk.Frame(parent, padding=(6, 4))
        ttk.Label(self.terminal_frame, text="Command line").pack(anchor=tk.W, pady=(0, 4))
        self.terminal_output = tk.Text(self.terminal_frame, height=6, wrap="word", font=("Menlo", 11))
        self.terminal_output.pack(fill=tk.X)
        self.terminal_output.configure(state=tk.DISABLED)
        self.terminal_input = ttk.Entry(self.terminal_frame)
        self.terminal_input.pack(fill=tk.X, pady=(4, 0))
        self.terminal_input.bind("<Return>", self._run_terminal_command)
        self.terminal_input.bind("<Escape>", lambda _e: self._hide_terminal())
        self.terminal_output.bind("<Escape>", lambda _e: self._hide_terminal())

    def _bind_keys(self) -> None:
        self.root.bind("<Tab>", lambda _e: self._switch_pane())
        self.root.bind("<Right>", self._handle_right_key)
        self.root.bind("<F3>", lambda _e: self._view_or_edit(editable=False))
        self.root.bind("<F4>", lambda _e: self._view_or_edit(editable=True))
        self.root.bind("<Shift-F4>", lambda _e: self._create_new_file())
        self.root.bind("<F5>", self._handle_copy_shortcut)
        self.root.bind("<F6>", self._handle_move_shortcut)
        self.root.bind_all("<F5>", self._handle_copy_shortcut, add="+")
        self.root.bind_all("<F6>", self._handle_move_shortcut, add="+")
        self.root.bind("<Command-r>", self._handle_copy_shortcut)
        self.root.bind("<Command-R>", self._handle_move_shortcut)
        self.root.bind_all("<Command-KeyPress-r>", self._handle_copy_shortcut, add="+")
        self.root.bind_all("<Command-KeyPress-R>", self._handle_move_shortcut, add="+")
        self.root.bind("<Shift-F6>", lambda _e: self._rename_selected())
        self.root.bind("<F7>", lambda _e: self._make_dir())
        self.root.bind("<F8>", lambda _e: self._delete_selected())
        self.root.bind("<Control-s>", lambda _e: self._clear_filter())
        self.root.bind("<Control-r>", self._handle_refresh_shortcut)
        self.root.bind("<Control-R>", self._handle_refresh_shortcut)
        self.root.bind_all("<Control-KeyPress-r>", self._handle_refresh_shortcut, add="+")
        self.root.bind_all("<Control-KeyPress-R>", self._handle_refresh_shortcut, add="+")
        self.root.bind("<Control-d>", self._handle_favorites_shortcut)
        self.root.bind("<Control-D>", self._handle_favorites_shortcut)
        self.root.bind_all("<Control-KeyPress-d>", self._handle_favorites_shortcut, add="+")
        self.root.bind_all("<Control-KeyPress-D>", self._handle_favorites_shortcut, add="+")

    def _handle_refresh_shortcut(self, _event: tk.Event | None = None) -> str:
        pane = self.active_pane if self.active_pane else self.left
        self._refresh_pane(pane, keep_selection=True)
        self.status_var.set(f"Refreshed: {self._zip_display_path(pane)}")
        return "break"

    def _handle_copy_shortcut(self, _event: tk.Event | None = None) -> str:
        self._copy_or_move(move=False)
        return "break"

    def _handle_move_shortcut(self, _event: tk.Event | None = None) -> str:
        self._copy_or_move(move=True)
        return "break"

    def _handle_favorites_shortcut(self, _event: tk.Event | None = None) -> str:
        return self._show_favorites_hotlist()

    def _handle_cross_pane_open(self, event: tk.Event) -> str | None:
        source_widget = event.widget if event.widget is not None else self.root.focus_get()
        if source_widget is self.left.tree and event.keysym == "Right":
            return self._open_selected_dir_in_other_pane(self.left)
        if source_widget is self.right.tree and event.keysym == "Left":
            return self._open_selected_dir_in_other_pane(self.right)
        return None

    def _handle_pane_secondary_click(self, event: tk.Event, pane: PaneState) -> str:
        self._set_active(pane)
        row_id = pane.tree.identify_row(event.y)
        if row_id:
            pane.tree.selection_set(row_id)
            pane.tree.focus(row_id)
        target = pane.zip_path if self._is_zip_mode(pane) and pane.zip_path else pane.current_path
        self._open_finder_context_menu(target)
        return "break"

    def _open_finder_context_menu(self, target: Path) -> None:
        script = """
on run argv
    set targetPath to item 1 of argv
    tell application "Finder"
        activate
        reveal POSIX file targetPath
    end tell
    delay 0.15
    tell application "System Events"
        tell process "Finder"
            set frontmost to true
            perform action "AXShowMenu" of first UI element of (first row of outline 1 of scroll area 1 of splitter group 1 of window 1 whose selected is true)
        end tell
    end tell
end run
"""
        try:
            completed = subprocess.run(
                ["osascript", "-e", script, str(target)],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            messagebox.showerror("Finder menu", f"Failed to open Finder menu:\n{exc}")
            return
        if completed.returncode != 0:
            self.status_var.set("Could not auto-open Finder context menu (check Accessibility permission).")

    def _pane_by_name(self, name: str) -> PaneState:
        return self.left if name == "Left" else self.right

    def _other_pane(self, pane: PaneState) -> PaneState:
        return self.right if pane is self.left else self.left

    def _set_active(self, pane: PaneState) -> None:
        self.active_pane = pane
        self.left.container.configure(highlightbackground="#6b6b6b")
        self.right.container.configure(highlightbackground="#6b6b6b")
        pane.container.configure(highlightbackground="#3e6794")
        other = self._other_pane(pane)
        other.tree.selection_remove(other.tree.selection())
        self.status_var.set(f"Active pane: {pane.name}")

    def _push_history(self, pane: PaneState, path: Path) -> None:
        if pane.current_path != path:
            pane.back_stack.append(pane.current_path)
            pane.forward_stack.clear()

    def _go_to_path(self, pane_name: str) -> None:
        pane = self._pane_by_name(pane_name)
        raw_target = pane.path_var.get().strip()
        if self._is_zip_mode(pane) and raw_target == self._zip_display_path(pane):
            return
        target = Path(raw_target).expanduser()
        if not target.exists() or not target.is_dir():
            messagebox.showerror("Invalid path", f"Not a directory: {target}")
            return
        pane.zip_path = None
        pane.zip_rel_dir = ""
        self._push_history(pane, target)
        pane.current_path = target.resolve()
        pane.path_var.set(str(pane.current_path))
        self._refresh_pane(pane, keep_selection=False)
        self._save_last_pane_paths()

    def _go_parent(self, pane_name: str) -> None:
        pane = self._pane_by_name(pane_name)
        if self._is_zip_mode(pane):
            if pane.zip_rel_dir:
                pane.zip_rel_dir = pane.zip_rel_dir.rsplit("/", 1)[0] if "/" in pane.zip_rel_dir else ""
                self._refresh_pane(pane, keep_selection=False)
                return
            archive = pane.zip_path
            pane.zip_path = None
            pane.zip_rel_dir = ""
            self._refresh_pane(pane, keep_selection=False)
            if archive:
                for idx, entry in enumerate(pane.entries):
                    if entry == archive:
                        self._select_index(pane, idx)
                        break
            return
        parent = pane.current_path.parent
        if parent == pane.current_path:
            return
        self._push_history(pane, parent)
        pane.current_path = parent
        pane.path_var.set(str(parent))
        self._refresh_pane(pane, keep_selection=False)
        self._save_last_pane_paths()

    def _load_last_pane_paths(self) -> tuple[Path, Path]:
        default_path = Path.cwd().resolve()
        if not self.state_file.exists():
            return default_path, default_path
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default_path, default_path
        if not isinstance(raw, dict):
            return default_path, default_path

        def resolve_dir(value: object) -> Path:
            if not isinstance(value, str):
                return default_path
            candidate = Path(value).expanduser()
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()
            return default_path

        return resolve_dir(raw.get("left")), resolve_dir(raw.get("right"))

    def _save_last_pane_paths(self) -> None:
        if not hasattr(self, "left") or not hasattr(self, "right"):
            return
        data = {"left": str(self.left.current_path), "right": str(self.right.current_path)}
        try:
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"Failed saving pane state: {exc}")

    def _on_close(self) -> None:
        self._save_last_pane_paths()
        self.root.destroy()

    def _load_favorites(self) -> None:
        if not self.favorites_file.exists():
            self.favorites = []
            return
        try:
            raw = json.loads(self.favorites_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.favorites = []
            self.status_var.set("Favorites file is invalid JSON; starting empty.")
            return
        except OSError as exc:
            self.favorites = []
            self.status_var.set(f"Failed loading favorites: {exc}")
            return
        if isinstance(raw, list):
            self.favorites = [p for p in raw if isinstance(p, str)]
        else:
            self.favorites = []

    def _save_favorites(self) -> None:
        try:
            self.favorites_file.write_text(json.dumps(self.favorites, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Favorites", f"Failed saving favorites:\n{exc}")

    def _add_current_to_favorites(self) -> str:
        pane = self.active_pane if self.active_pane else self.left
        current = str(pane.current_path)
        if current in self.favorites:
            self.status_var.set("Already in favorites")
            return "break"
        self.favorites.append(current)
        self.favorites.sort(key=str.lower)
        self._save_favorites()
        self.status_var.set(f"Added to favorites: {current}")
        return "break"

    def _show_favorites_hotlist(self) -> str:
        pane = self.active_pane if self.active_pane else self.left
        window = tk.Toplevel(self.root)
        window.title("Favorites Hotlist")
        window.geometry("700x420")

        frame = ttk.Frame(window, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        listbox = tk.Listbox(frame, font=("Menlo", 12))
        listbox.pack(fill=tk.BOTH, expand=True)
        for favorite in self.favorites:
            listbox.insert(tk.END, favorite)
        if listbox.size() > 0:
            listbox.selection_set(0)
            listbox.activate(0)
        listbox.focus_set()

        buttons = ttk.Frame(window, padding=8)
        buttons.pack(fill=tk.X)

        def move(delta: int) -> None:
            if listbox.size() == 0:
                return
            selected = listbox.curselection()
            current = selected[0] if selected else 0
            target_idx = min(max(current + delta, 0), listbox.size() - 1)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(target_idx)
            listbox.activate(target_idx)
            listbox.see(target_idx)

        def move_up() -> str:
            move(-1)
            return "break"

        def move_down() -> str:
            move(1)
            return "break"

        def go_selected() -> None:
            selected = listbox.curselection()
            if not selected:
                return
            target = Path(listbox.get(selected[0]))
            if not target.exists() or not target.is_dir():
                messagebox.showerror("Favorites", f"Path not found:\n{target}")
                return
            self._push_history(pane, target)
            pane.zip_path = None
            pane.zip_rel_dir = ""
            pane.current_path = target.resolve()
            pane.path_var.set(str(pane.current_path))
            self._refresh_pane(pane, keep_selection=False)
            self._set_active(pane)
            pane.tree.focus_set()
            self._save_last_pane_paths()
            window.destroy()

        def add_current() -> None:
            current = str(pane.current_path)
            if current in self.favorites:
                self.status_var.set("Already in favorites")
                return
            self.favorites.append(current)
            self.favorites.sort(key=str.lower)
            self._save_favorites()
            listbox.delete(0, tk.END)
            for favorite in self.favorites:
                listbox.insert(tk.END, favorite)
            selected_idx = self.favorites.index(current)
            listbox.selection_set(selected_idx)
            listbox.activate(selected_idx)
            listbox.see(selected_idx)
            self.status_var.set(f"Added to favorites: {current}")

        def remove_selected() -> None:
            selected = listbox.curselection()
            if not selected:
                return
            value = listbox.get(selected[0])
            self.favorites = [p for p in self.favorites if p != value]
            self._save_favorites()
            listbox.delete(selected[0])
            if listbox.size() > 0:
                new_idx = min(selected[0], listbox.size() - 1)
                listbox.selection_set(new_idx)
                listbox.activate(new_idx)
                listbox.see(new_idx)

        def close_hotlist(_event: tk.Event | None = None) -> str:
            window.destroy()
            return "break"

        ttk.Button(buttons, text="Add current", command=add_current).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Go", command=go_selected).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Remove", command=remove_selected).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side=tk.RIGHT, padx=4)

        listbox.bind("<Up>", lambda _e: move_up())
        listbox.bind("<Down>", lambda _e: move_down())
        listbox.bind("<Double-Button-1>", lambda _e: go_selected())
        listbox.bind("<Return>", lambda _e: go_selected())
        listbox.bind("<Escape>", close_hotlist)
        window.bind("<Escape>", close_hotlist)
        return "break"

    def _format_size(self, path: Path) -> str:
        if path.is_dir():
            return "<DIR>"
        try:
            size = path.stat().st_size
        except OSError:
            return "?"
        return self._format_size_bytes(size)

    def _format_size_bytes(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        unit = units[0]
        for u in units:
            unit = u
            if value < 1024 or u == units[-1]:
                break
            value /= 1024
        if unit == "B":
            return f"{int(value)} {unit}"
        return f"{value:.1f} {unit}"

    def _format_modified(self, path: Path) -> str:
        try:
            ts = path.stat().st_mtime
        except OSError:
            return "?"
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    def _is_zip_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".zip"

    def _is_zip_mode(self, pane: PaneState) -> bool:
        return pane.zip_path is not None

    def _zip_display_path(self, pane: PaneState) -> str:
        if not pane.zip_path:
            return str(pane.current_path)
        rel = pane.zip_rel_dir.strip("/")
        inside = f"/{rel}" if rel else "/"
        return f"{pane.zip_path}::{inside}"

    def _sort_key(self, path: Path, column: str) -> tuple:
        if column == "size":
            try:
                value = path.stat().st_size if path.is_file() else -1
            except OSError:
                value = -1
            return (value, path.name.lower())
        if column == "ext":
            return (path.suffix.lower(), path.name.lower())
        if column == "modified":
            try:
                value = path.stat().st_mtime
            except OSError:
                value = 0.0
            return (value, path.name.lower())
        return (path.name.lower(),)

    def _sort_children(self, pane: PaneState, children: list[Path]) -> list[Path]:
        dirs = [p for p in children if p.is_dir()]
        files = [p for p in children if not p.is_dir()]
        dirs_sorted = sorted(dirs, key=lambda p: self._sort_key(p, pane.sort_column), reverse=pane.sort_desc)
        files_sorted = sorted(files, key=lambda p: self._sort_key(p, pane.sort_column), reverse=pane.sort_desc)
        return dirs_sorted + files_sorted

    def _sort_zip_entries(self, pane: PaneState, entries: list[ZipPaneEntry]) -> list[ZipPaneEntry]:
        def key(entry: ZipPaneEntry) -> tuple:
            if pane.sort_column == "size":
                return (entry.size if not entry.is_dir else -1, entry.name.lower())
            if pane.sort_column == "ext":
                return (Path(entry.name).suffix.lower(), entry.name.lower())
            if pane.sort_column == "modified":
                return (entry.modified_ts or 0.0, entry.name.lower())
            return (entry.name.lower(),)

        dirs = [entry for entry in entries if entry.is_dir]
        files = [entry for entry in entries if not entry.is_dir]
        return sorted(dirs, key=key, reverse=pane.sort_desc) + sorted(files, key=key, reverse=pane.sort_desc)

    def _update_sort_headings(self, pane: PaneState) -> None:
        labels = {"name": "Name", "size": "Size", "ext": "Ext", "modified": "Last Modified"}
        for col, base in labels.items():
            marker = ""
            if pane.sort_column == col:
                marker = " ▼" if pane.sort_desc else " ▲"
            pane.tree.heading(
                col,
                text=f"{base}{marker}",
                command=lambda c=col, p=pane: self._set_sort(p, c),
            )

    def _set_sort(self, pane: PaneState, column: str) -> None:
        if pane.sort_column == column:
            pane.sort_desc = not pane.sort_desc
        else:
            pane.sort_column = column
            pane.sort_desc = False
        self._update_sort_headings(pane)
        self._refresh_pane(pane, keep_selection=True)
        self.status_var.set(
            f"{pane.name} sort: {pane.sort_column} {'desc' if pane.sort_desc else 'asc'}"
        )

    def _handle_tree_double_click(self, event: tk.Event, pane: PaneState) -> str:
        region = pane.tree.identify_region(event.x, event.y)
        if region == "separator":
            self._autosize_column_from_separator(pane, event.x)
            return "break"
        if region in {"cell", "tree"}:
            self._open_selected(pane)
            return "break"
        return "break"

    def _autosize_column_from_separator(self, pane: PaneState, x_position: int) -> None:
        cols = ("name", "size", "ext", "modified")
        widths = [int(pane.tree.column(c, "width")) for c in cols]
        running = 0
        target_index = None
        for i, width in enumerate(widths):
            running += width
            if abs(running - x_position) <= 8:
                target_index = i
                break
        if target_index is None:
            return
        self._autosize_column(pane, cols[target_index])

    def _autosize_column(self, pane: PaneState, column: str) -> None:
        min_width = {"name": 180, "size": 90, "ext": 60, "modified": 140}
        cols = ("name", "size", "ext", "modified")
        pane.tree.update_idletasks()
        tree_width = pane.tree.winfo_width()
        if tree_width <= 1:
            return

        current_widths = {c: int(pane.tree.column(c, "width")) for c in cols}
        available_for_target = tree_width - sum(current_widths[c] for c in cols if c != column)
        if available_for_target <= min_width[column]:
            self.status_var.set(f"Not enough room to auto-size {column}.")
            return

        style = ttk.Style(pane.tree)
        style_name = str(pane.tree.cget("style") or "Treeview")
        font_spec = style.lookup(style_name, "font") or style.lookup("Treeview", "font") or "TkDefaultFont"
        try:
            font = tkfont.nametofont(str(font_spec))
        except tk.TclError:
            font = tkfont.Font(font=font_spec)
        heading_text = str(pane.tree.heading(column, "text")).replace(" ▲", "").replace(" ▼", "")
        longest = font.measure(heading_text)
        col_index = cols.index(column)
        for iid in pane.tree.get_children():
            values = pane.tree.item(iid, "values")
            value = str(values[col_index]) if col_index < len(values) else ""
            longest = max(longest, font.measure(value))
        desired = longest + 24
        final_width = max(min_width[column], min(desired, available_for_target))
        pane.tree.column(column, width=final_width)
        self.status_var.set(f"Auto-sized {column} column.")

    def _recenter_splitter_if_clicked(self, event: tk.Event) -> str | None:
        try:
            sash_x = int(self.panes.sashpos(0))
        except tk.TclError:
            return None
        if abs(event.x - sash_x) > 10:
            return None
        total = self.panes.winfo_width()
        if total <= 1:
            return None
        self.panes.sashpos(0, total // 2)
        self.status_var.set("Pane divider centered")
        return "break"

    def _refresh_pane(self, pane: PaneState, keep_selection: bool = True) -> None:
        if self._is_zip_mode(pane):
            self._refresh_zip_pane(pane, keep_selection=keep_selection)
            return
        previous_path = self._selected_path(pane) if keep_selection else None
        pane.tree.delete(*pane.tree.get_children())
        pane.entries = [None]
        pane.tree.insert("", tk.END, iid="0", values=("..", "", "", ""))
        try:
            children = list(pane.current_path.iterdir())
        except PermissionError:
            messagebox.showerror("Permission denied", f"Cannot open {pane.current_path}")
            return
        if pane is self.active_pane and self.filter_query:
            children = [p for p in children if self._matches_filter(p.name, self.filter_query)]
        children = self._sort_children(pane, children)

        for idx, child in enumerate(children, start=1):
            pane.entries.append(child)
            name = f"{child.name}/" if child.is_dir() else child.name
            ext = "" if child.is_dir() else child.suffix.lstrip(".")
            tags = ("marked",) if child in pane.marks else ()
            pane.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(name, self._format_size(child), ext, self._format_modified(child)),
                tags=tags,
            )

        pane.path_var.set(str(pane.current_path))
        if pane.entries:
            selection = 0
            if pane is self.active_pane and self.filter_query and len(pane.entries) > 1:
                selection = 1
            if previous_path:
                for idx, entry in enumerate(pane.entries):
                    if entry == previous_path:
                        selection = idx
                        break
            self._select_index(pane, selection)

    def _refresh_zip_pane(self, pane: PaneState, keep_selection: bool = True) -> None:
        if not pane.zip_path:
            return
        previous_entry = self._selected_zip_entry(pane) if keep_selection else None
        pane.tree.delete(*pane.tree.get_children())
        pane.entries = [None]
        pane.tree.insert("", tk.END, iid="0", values=("..", "", "", ""))
        prefix = f"{pane.zip_rel_dir.strip('/')}/" if pane.zip_rel_dir.strip("/") else ""
        dir_entries: dict[str, ZipPaneEntry] = {}
        file_entries: list[ZipPaneEntry] = []
        try:
            with zipfile.ZipFile(pane.zip_path) as zf:
                for info in zf.infolist():
                    filename = info.filename.strip("/")
                    if not filename:
                        continue
                    if prefix and not filename.startswith(prefix):
                        continue
                    remainder = filename[len(prefix):] if prefix else filename
                    if not remainder:
                        continue
                    head, _, tail = remainder.partition("/")
                    rel_path = f"{prefix}{head}".strip("/")
                    if tail:
                        if rel_path not in dir_entries:
                            dir_entries[rel_path] = ZipPaneEntry(rel_path=rel_path, name=head, is_dir=True)
                        continue
                    modified_ts = None
                    try:
                        modified_ts = datetime(*info.date_time).timestamp()
                    except ValueError:
                        modified_ts = None
                    file_entries.append(
                        ZipPaneEntry(
                            rel_path=rel_path,
                            name=head,
                            is_dir=info.is_dir(),
                            size=0 if info.is_dir() else info.file_size,
                            modified_ts=modified_ts,
                        )
                    )
        except (FileNotFoundError, zipfile.BadZipFile, OSError) as exc:
            messagebox.showerror("ZIP", f"Cannot open archive:\n{exc}")
            pane.zip_path = None
            pane.zip_rel_dir = ""
            self._refresh_pane(pane, keep_selection=True)
            return

        entries = list(dir_entries.values()) + file_entries
        if pane is self.active_pane and self.filter_query:
            entries = [entry for entry in entries if self._matches_filter(entry.name, self.filter_query)]
        entries = self._sort_zip_entries(pane, entries)
        for idx, entry in enumerate(entries, start=1):
            pane.entries.append(entry)
            ext = "" if entry.is_dir else Path(entry.name).suffix.lstrip(".")
            size = "<DIR>" if entry.is_dir else self._format_size_bytes(entry.size)
            modified = "?" if entry.modified_ts is None else datetime.fromtimestamp(entry.modified_ts).strftime("%Y-%m-%d %H:%M")
            pane.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(f"{entry.name}/" if entry.is_dir else entry.name, size, ext, modified),
            )

        pane.path_var.set(self._zip_display_path(pane))
        selection = 0
        if pane is self.active_pane and self.filter_query and len(pane.entries) > 1:
            selection = 1
        if previous_entry:
            for idx, entry in enumerate(pane.entries):
                if entry == previous_entry:
                    selection = idx
                    break
        self._select_index(pane, selection)

    def _matches_filter(self, name: str, query: str) -> bool:
        if "*" in query:
            pattern = "^" + "".join(".*" if ch == "*" else re.escape(ch) for ch in query) + ".*"
        else:
            pattern = "^" + re.escape(query) + ".*"
        return re.match(pattern, name, flags=re.IGNORECASE) is not None

    def _apply_filter(self) -> None:
        if self.filter_mode:
            self.filter_var.set(f"Search: {self.filter_query}")
        else:
            self.filter_var.set("")
        self._refresh_pane(self.left, keep_selection=True)
        self._refresh_pane(self.right, keep_selection=True)
        if self.active_pane:
            self.active_pane.tree.focus_set()

    def _clear_filter(self) -> str:
        if not self.filter_mode and not self.filter_query:
            return "break"
        self.filter_mode = False
        self.filter_query = ""
        self._apply_filter()
        self.status_var.set("Search mode exited")
        return "break"

    def _selected_index(self, pane: PaneState) -> int | None:
        selected = pane.tree.selection()
        if not selected:
            return None
        try:
            return int(selected[0])
        except ValueError:
            return None

    def _selected_path(self, pane: PaneState) -> Path | None:
        if self._is_zip_mode(pane):
            return None
        idx = self._selected_index(pane)
        if idx is None or idx >= len(pane.entries):
            return None
        entry = pane.entries[idx]
        return pane.current_path.parent if entry is None else entry

    def _selected_zip_entry(self, pane: PaneState) -> ZipPaneEntry | None:
        if not self._is_zip_mode(pane):
            return None
        idx = self._selected_index(pane)
        if idx is None or idx >= len(pane.entries):
            return None
        entry = pane.entries[idx]
        return entry if isinstance(entry, ZipPaneEntry) else None

    def _select_index(self, pane: PaneState, idx: int) -> None:
        if idx < 0 or idx >= len(pane.entries):
            return
        pane.tree.selection_set(str(idx))
        pane.tree.focus(str(idx))
        pane.tree.see(str(idx))

    def _open_selected(self, pane: PaneState) -> None:
        if self._is_zip_mode(pane):
            entry = self._selected_zip_entry(pane)
            should_clear_filter = pane is self.active_pane and (self.filter_mode or bool(self.filter_query))
            if entry is None:
                self._go_parent(pane.name)
            elif entry.is_dir:
                pane.zip_rel_dir = entry.rel_path
                self._refresh_pane(pane, keep_selection=False)
            else:
                self.status_var.set("Use F5 to extract files from ZIP to the other pane.")
            if should_clear_filter:
                self.filter_mode = False
                self.filter_query = ""
                self._apply_filter()
            return
        target = self._selected_path(pane)
        if not target:
            return
        should_clear_filter = pane is self.active_pane and (self.filter_mode or bool(self.filter_query))
        if target.is_dir():
            self._push_history(pane, target)
            pane.current_path = target
            pane.path_var.set(str(target))
            self._refresh_pane(pane, keep_selection=False)
            self._save_last_pane_paths()
        elif self._is_zip_file(target):
            pane.zip_path = target.resolve()
            pane.zip_rel_dir = ""
            pane.path_var.set(self._zip_display_path(pane))
            self._refresh_pane(pane, keep_selection=False)
            self.status_var.set(f"Opened ZIP: {pane.zip_path}")
        else:
            self._open_external(target)
        if should_clear_filter:
            self.filter_mode = False
            self.filter_query = ""
            self._apply_filter()

    def _open_selected_dir_in_other_pane(self, source_pane: PaneState) -> str:
        target = self._selected_path(source_pane)
        if not target or not target.is_dir():
            self.status_var.set("Select a directory to open in the other pane.")
            return "break"
        other = self._other_pane(source_pane)
        resolved_target = target.resolve()
        self._push_history(other, resolved_target)
        other.zip_path = None
        other.zip_rel_dir = ""
        other.current_path = resolved_target
        other.path_var.set(str(resolved_target))
        self._refresh_pane(other, keep_selection=False)
        self._set_active(other)
        other.tree.focus_set()
        self._save_last_pane_paths()
        self.status_var.set(f"Opened in {other.name}: {resolved_target}")
        return "break"

    def _toggle_mark_current(self, pane: PaneState) -> str:
        if self._is_zip_mode(pane):
            self.status_var.set("Marking inside ZIP is not supported.")
            return "break"
        idx = self._selected_index(pane)
        if idx is None:
            return "break"
        target = pane.entries[idx]
        if target is not None:
            if target in pane.marks:
                pane.marks.remove(target)
            else:
                pane.marks.add(target)
        self._refresh_pane(pane, keep_selection=False)
        self._select_index(pane, idx)
        return "break"

    def _handle_backspace(self, pane: PaneState) -> str:
        if self.filter_mode:
            if self.filter_query:
                self.filter_query = self.filter_query[:-1]
            self._apply_filter()
            return "break"
        self._go_parent(pane.name)
        return "break"

    def _handle_keypress(self, event: tk.Event, pane: PaneState) -> str | None:
        if pane is not self.active_pane:
            return None
        if event.keysym == "F5":
            return self._handle_copy_shortcut()
        if event.keysym == "F6":
            return self._handle_move_shortcut()
        modifier_pressed = bool(event.state & 0x4 or event.state & 0x8)
        if modifier_pressed and event.keysym in {"Right", "KP_Right"} and pane is self.left:
            return self._open_selected_dir_in_other_pane(pane)
        if modifier_pressed and event.keysym in {"Left", "KP_Left"} and pane is self.right:
            return self._open_selected_dir_in_other_pane(pane)
        if event.keysym in {"Up", "Down", "Left", "Right", "Return", "Tab", "Escape", "BackSpace", "space"}:
            return None
        if modifier_pressed:
            return None
        if not event.char or not event.char.isprintable():
            return None
        self.filter_mode = True
        self.filter_query += event.char
        self._apply_filter()
        return "break"

    def _effective_selection(self, pane: PaneState) -> list[Path]:
        if self._is_zip_mode(pane):
            return []
        if pane.marks:
            return sorted(pane.marks, key=lambda p: p.name.lower())
        one = self._selected_path(pane)
        if one is None or one == pane.current_path.parent:
            return []
        return [one]

    def _effective_zip_selection(self, pane: PaneState) -> list[ZipPaneEntry]:
        if not self._is_zip_mode(pane):
            return []
        one = self._selected_zip_entry(pane)
        if one is None:
            return []
        return [one]

    def _select_copy_move_name(self) -> None:
        if not self.copy_move_name_entry:
            return
        filename = self.copy_move_name_entry.get()
        self.copy_move_name_entry.focus_set()
        self.copy_move_name_entry.selection_clear()
        if self.copy_move_select_mode == "name":
            dot = filename.rfind(".")
            end = dot if dot > 0 else len(filename)
            self.copy_move_name_entry.selection_range(0, end)
        else:
            self.copy_move_name_entry.selection_range(0, tk.END)
        self.copy_move_name_entry.icursor(tk.END)

    def _toggle_copy_move_selection(self) -> None:
        self.copy_move_select_mode = "full" if self.copy_move_select_mode == "name" else "name"
        self._select_copy_move_name()

    def _show_copy_move_dialog(
        self,
        move: bool,
        items: list[Path | ZipPaneEntry],
        default_target_dir: Path,
    ) -> tuple[Path, str | None] | None:
        action = "Move" if move else "Copy"
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{action} ({'F6' if move else 'F5'})")
        dialog.geometry("700x190")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self.copy_move_dialog = dialog
        self.copy_move_name_entry = None
        self.copy_move_select_mode = "name"

        result: dict[str, Path | str | bool | None] = {"ok": False, "target_dir": None, "new_name": None}

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        first_name = items[0].name if items else ""
        ttk.Label(
            frame,
            text=f"{action} {len(items)} item(s)\nSource: {first_name}",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))

        target_var = tk.StringVar(value=str(default_target_dir))
        ttk.Label(frame, text="Target directory:").pack(anchor=tk.W)
        target_entry = ttk.Entry(frame, textvariable=target_var)
        target_entry.pack(fill=tk.X, pady=(0, 8))

        name_var: tk.StringVar | None = None
        if len(items) == 1:
            name_var = tk.StringVar(value=first_name)
            ttk.Label(frame, text="Target file name:").pack(anchor=tk.W)
            name_entry = ttk.Entry(frame, textvariable=name_var)
            name_entry.pack(fill=tk.X, pady=(0, 8))
            self.copy_move_name_entry = name_entry

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)

        def submit() -> None:
            target_dir = Path(target_var.get()).expanduser()
            if not target_dir.exists() or not target_dir.is_dir():
                messagebox.showerror(action, f"Target directory not found:\n{target_dir}", parent=dialog)
                return
            new_name = name_var.get().strip() if name_var else None
            if name_var is not None and not new_name:
                messagebox.showerror(action, "Target file name cannot be empty.", parent=dialog)
                return
            result["ok"] = True
            result["target_dir"] = target_dir.resolve()
            result["new_name"] = new_name
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        ttk.Button(buttons, text=action, command=submit).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side=tk.RIGHT, padx=4)

        def handle_toggle(_event: tk.Event) -> str:
            if self.copy_move_name_entry:
                self._toggle_copy_move_selection()
                return "break"
            return "break"

        dialog.bind("<Return>", lambda _e: submit())
        dialog.bind("<Escape>", lambda _e: cancel())
        dialog.bind("<F5>", handle_toggle)
        dialog.bind("<F6>", handle_toggle)
        if self.copy_move_name_entry:
            dialog.after(40, self._select_copy_move_name)
        else:
            target_entry.focus_set()

        self.root.wait_window(dialog)
        self.copy_move_dialog = None
        self.copy_move_name_entry = None
        if result["ok"]:
            return result["target_dir"], result["new_name"]
        return None

    def _copy_or_move(self, move: bool) -> None:
        if self.copy_move_dialog and self.copy_move_dialog.winfo_exists():
            if self.copy_move_name_entry:
                self._toggle_copy_move_selection()
            return
        pane = self.active_pane
        if not pane:
            return
        if self._is_zip_mode(pane):
            self._copy_from_zip(move=move, pane=pane)
            return
        items = self._effective_selection(pane)
        if not items:
            messagebox.showinfo("No selection", "Select or mark files/directories first.")
            return
        other = self._other_pane(pane)
        if self._is_zip_mode(other):
            messagebox.showinfo("Copy/Move", "Target pane must be a filesystem directory, not a ZIP view.")
            return
        target_dir = other.current_path
        action = "Move" if move else "Copy"
        dialog_result = self._show_copy_move_dialog(move=move, items=items, default_target_dir=target_dir)
        if not dialog_result:
            return
        target_dir, new_name = dialog_result
        copied = 0
        for idx, src in enumerate(items):
            destination_name = new_name if (new_name and len(items) == 1 and idx == 0) else src.name
            dest = target_dir / destination_name
            try:
                if dest.exists():
                    overwrite = messagebox.askyesno("Overwrite?", f"{dest} exists. Replace it?")
                    if not overwrite:
                        continue
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                if move:
                    shutil.move(str(src), str(dest))
                elif src.is_dir():
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
                copied += 1
            except FileNotFoundError as exc:
                messagebox.showerror(action, f"Source not found:\n{exc}")
                break
            except PermissionError as exc:
                messagebox.showerror(action, f"Permission denied:\n{exc}")
                break
            except OSError as exc:
                messagebox.showerror(action, f"Operation failed:\n{exc}")
                break
        pane.marks.difference_update(items)
        self._refresh_pane(pane)
        self._refresh_pane(other, keep_selection=False)
        self.status_var.set(f"{action} completed for {copied} item(s).")

    def _copy_from_zip(self, move: bool, pane: PaneState) -> None:
        if move:
            messagebox.showinfo("Move", "Moving from inside ZIP is not supported. Use F5 to extract.")
            return
        if not pane.zip_path:
            return
        items = self._effective_zip_selection(pane)
        if not items:
            messagebox.showinfo("No selection", "Select a file or directory inside the ZIP first.")
            return
        other = self._other_pane(pane)
        if self._is_zip_mode(other):
            messagebox.showinfo("Copy", "Target pane must be a filesystem directory, not another ZIP.")
            return
        target_dir = other.current_path
        dialog_result = self._show_copy_move_dialog(move=False, items=items, default_target_dir=target_dir)
        if not dialog_result:
            return
        target_dir, new_name = dialog_result
        copied = 0
        try:
            with zipfile.ZipFile(pane.zip_path) as zf, tempfile.TemporaryDirectory() as tmp_dir:
                tmp_root = Path(tmp_dir)
                for idx, entry in enumerate(items):
                    destination_name = new_name if (new_name and len(items) == 1 and idx == 0) else entry.name
                    dest = target_dir / destination_name
                    if dest.exists():
                        overwrite = messagebox.askyesno("Overwrite?", f"{dest} exists. Replace it?")
                        if not overwrite:
                            continue
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    try:
                        self._extract_zip_entry(zf, entry, tmp_root, dest)
                    except KeyError as exc:
                        messagebox.showerror("Copy", f"ZIP entry not found:\n{exc}")
                        break
                    except PermissionError as exc:
                        messagebox.showerror("Copy", f"Permission denied:\n{exc}")
                        break
                    except OSError as exc:
                        messagebox.showerror("Copy", f"Extraction failed:\n{exc}")
                        break
                    copied += 1
        except (FileNotFoundError, zipfile.BadZipFile, OSError) as exc:
            messagebox.showerror("Copy", f"Cannot open ZIP:\n{exc}")
            return
        self._refresh_pane(pane, keep_selection=True)
        self._refresh_pane(other, keep_selection=False)
        self.status_var.set(f"Copied {copied} item(s) from ZIP.")

    def _extract_zip_entry(self, zf: zipfile.ZipFile, entry: ZipPaneEntry, tmp_root: Path, dest: Path) -> None:
        if entry.is_dir:
            prefix = entry.rel_path.strip("/") + "/"
            members = [info for info in zf.infolist() if info.filename.startswith(prefix)]
            if not members:
                dest.mkdir(parents=True, exist_ok=True)
                return
            zf.extractall(path=tmp_root, members=[info.filename for info in members])
            src = tmp_root / entry.rel_path
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                dest.mkdir(parents=True, exist_ok=True)
            return
        extracted = zf.extract(entry.rel_path, path=tmp_root)
        shutil.copy2(Path(extracted), dest)

    def _delete_selected(self) -> None:
        pane = self.active_pane
        if not pane:
            return
        if self._is_zip_mode(pane):
            messagebox.showinfo("Delete", "Delete is not supported while browsing inside a ZIP.")
            return
        items = self._effective_selection(pane)
        if not items:
            messagebox.showinfo("No selection", "Select or mark files/directories first.")
            return
        if not messagebox.askyesno("Delete", f"Delete {len(items)} item(s) permanently?"):
            return
        deleted = 0
        for item in items:
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1
            except FileNotFoundError as exc:
                messagebox.showerror("Delete", f"Item not found:\n{exc}")
                break
            except PermissionError as exc:
                messagebox.showerror("Delete", f"Permission denied:\n{exc}")
                break
            except OSError as exc:
                messagebox.showerror("Delete", f"Delete failed:\n{exc}")
                break
        pane.marks.difference_update(items)
        self._refresh_pane(pane, keep_selection=False)
        self.status_var.set(f"Deleted {deleted} item(s).")

    def _make_dir(self) -> None:
        pane = self.active_pane
        if not pane:
            return
        if self._is_zip_mode(pane):
            messagebox.showinfo("Create directory", "Create directory is not supported inside a ZIP.")
            return
        name = simpledialog.askstring("Create directory", "Directory name:")
        if not name:
            return
        new_dir = pane.current_path / name
        try:
            new_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            messagebox.showerror("Create directory", f"Already exists:\n{new_dir}")
            return
        except PermissionError as exc:
            messagebox.showerror("Create directory", f"Permission denied:\n{exc}")
            return
        self._refresh_pane(pane, keep_selection=False)
        self.status_var.set(f"Created directory: {new_dir}")

    def _view_or_edit(self, editable: bool) -> None:
        pane = self.active_pane
        if not pane:
            return
        if self._is_zip_mode(pane):
            messagebox.showinfo("No file", "View/Edit inside ZIP is not supported yet. Use F5 to extract first.")
            return
        target = self._selected_path(pane)
        if target is None or target.is_dir():
            messagebox.showinfo("No file", "Select a file to view/edit.")
            return
        self._open_text_window(target, editable=editable)

    def _create_new_file(self) -> str:
        pane = self.active_pane
        if not pane:
            return "break"
        if self._is_zip_mode(pane):
            messagebox.showinfo("Create file", "Creating files inside ZIP is not supported.")
            return "break"
        name = simpledialog.askstring("Create file (Shift+F4)", "New file name:")
        if not name:
            return "break"
        new_file = pane.current_path / name
        if new_file.exists():
            messagebox.showerror("Create file", f"Already exists:\n{new_file}")
            return "break"
        try:
            new_file.touch(exist_ok=False)
        except PermissionError as exc:
            messagebox.showerror("Create file", f"Permission denied:\n{exc}")
            return "break"
        except OSError as exc:
            messagebox.showerror("Create file", f"Create failed:\n{exc}")
            return "break"
        self._refresh_pane(pane, keep_selection=False)
        for idx, entry in enumerate(pane.entries):
            if entry == new_file:
                self._select_index(pane, idx)
                break
        self._open_text_window(new_file, editable=True)
        self.status_var.set(f"Created file: {new_file}")
        return "break"

    def _open_text_window(self, path: Path, editable: bool) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"{'Edit' if editable else 'View'} - {path.name}")
        window.geometry("900x650")

        text = tk.Text(window, wrap="none", font=("Menlo", 12))
        text.pack(fill=tk.BOTH, expand=True)
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text.insert("1.0", f.read())
        text.focus_set()

        if not editable:
            def close_view(_event: tk.Event | None = None) -> str:
                window.destroy()
                return "break"

            window.protocol("WM_DELETE_WINDOW", window.destroy)
            text.bind("<Escape>", close_view)
            text.configure(state=tk.DISABLED)
            return

        buttons = ttk.Frame(window, padding=6)
        buttons.pack(fill=tk.X)
        last_saved_content = text.get("1.0", "end-1c")

        def save() -> bool:
            nonlocal last_saved_content
            data = text.get("1.0", "end-1c")
            try:
                with path.open("w", encoding="utf-8") as f:
                    f.write(data)
                    f.write("\n")
            except PermissionError as exc:
                messagebox.showerror("Save", f"Permission denied:\n{exc}")
                return False
            except OSError as exc:
                messagebox.showerror("Save", f"Write failed:\n{exc}")
                return False
            last_saved_content = data
            self.status_var.set(f"Saved: {path}")
            return True

        def save_shortcut(_event: tk.Event | None = None) -> str:
            save()
            return "break"

        def close_editor(_event: tk.Event | None = None) -> str:
            current = text.get("1.0", "end-1c")
            if current == last_saved_content:
                window.destroy()
                return "break"
            choice = messagebox.askyesnocancel(
                "Unsaved changes",
                f"Save changes to {path.name} before closing?",
                parent=window,
            )
            if choice is None:
                return "break"
            if choice and not save():
                return "break"
            window.destroy()
            return "break"

        def on_window_close() -> None:
            close_editor()

        ttk.Button(buttons, text="Save", command=save).pack(side=tk.RIGHT)
        text.bind("<Control-s>", save_shortcut)
        text.bind("<Control-S>", save_shortcut)
        text.bind("<Escape>", close_editor)
        window.protocol("WM_DELETE_WINDOW", on_window_close)

    def _open_external(self, path: Path) -> None:
        if os.name == "posix":
            subprocess.Popen(["open", str(path)])
        else:
            messagebox.showinfo("Open", f"File selected: {path}")

    def _switch_pane(self) -> str:
        source = self.active_pane if self.active_pane else self.left
        target = self.right if source is self.left else self.left
        source_idx = self._selected_index(source)
        target_idx = 0 if source_idx is None else min(source_idx, max(len(target.entries) - 1, 0))
        self._select_index(target, target_idx)
        target.tree.focus_set()
        self._set_active(target)
        return "break"

    def _move_selection(self, delta: int) -> str:
        pane = self.active_pane
        if not pane or not pane.entries:
            return "break"
        current = self._selected_index(pane)
        if current is None:
            current = 0
        next_idx = min(max(current + delta, 0), len(pane.entries) - 1)
        self._select_index(pane, next_idx)
        pane.tree.focus_set()
        return "break"

    def _rename_selected(self) -> str:
        pane = self.active_pane
        if not pane:
            return "break"
        if self._is_zip_mode(pane):
            messagebox.showinfo("Rename", "Renaming inside ZIP is not supported.")
            return "break"
        target = self._selected_path(pane)
        if target is None or target == pane.current_path.parent:
            messagebox.showinfo("Rename", "Select a file or directory to rename.")
            return "break"
        new_name = simpledialog.askstring("Rename", "New name:", initialvalue=target.name)
        if not new_name or new_name == target.name:
            return "break"
        new_path = target.with_name(new_name)
        if new_path.exists():
            messagebox.showerror("Rename", f"Target already exists:\n{new_path}")
            return "break"
        try:
            target.rename(new_path)
        except PermissionError as exc:
            messagebox.showerror("Rename", f"Permission denied:\n{exc}")
            return "break"
        except OSError as exc:
            messagebox.showerror("Rename", f"Rename failed:\n{exc}")
            return "break"
        if target in pane.marks:
            pane.marks.remove(target)
            pane.marks.add(new_path)
        self._refresh_pane(pane, keep_selection=False)
        for idx, entry in enumerate(pane.entries):
            if entry == new_path:
                self._select_index(pane, idx)
                break
        self.status_var.set(f"Renamed to: {new_name}")
        return "break"

    def _show_terminal(self) -> None:
        if not self.terminal_visible:
            self.terminal_frame.pack(fill=tk.X, before=self.status_bar)
            self.terminal_visible = True
        self.terminal_input.focus_set()
        if self.active_pane:
            self.status_var.set(f"Terminal cwd: {self._zip_display_path(self.active_pane)}")

    def _hide_terminal(self) -> str:
        if self.terminal_visible:
            self.terminal_frame.pack_forget()
            self.terminal_visible = False
            if self.active_pane:
                self.active_pane.tree.focus_set()
        return "break"

    def _handle_right_key(self, _event: tk.Event) -> str | None:
        focus_widget = self.root.focus_get()
        if focus_widget in (self.left.tree, self.right.tree):
            self._show_terminal()
            return "break"
        return None

    def _append_terminal_output(self, text: str) -> None:
        self.terminal_output.configure(state=tk.NORMAL)
        self.terminal_output.insert(tk.END, text)
        self.terminal_output.see(tk.END)
        self.terminal_output.configure(state=tk.DISABLED)

    def _run_terminal_command(self, _event: tk.Event) -> str:
        command = self.terminal_input.get().strip()
        if not command:
            return "break"
        pane = self.active_pane if self.active_pane else self.left
        if self._is_zip_mode(pane):
            self._append_terminal_output("Error: terminal commands are disabled while browsing inside ZIP.\n")
            self.status_var.set("Exit ZIP view to use terminal commands.")
            return "break"
        self._append_terminal_output(f"$ {command}\n")
        try:
            completed = subprocess.run(
                command,
                cwd=str(pane.current_path),
                shell=True,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            self._append_terminal_output(f"Error: {exc}\n")
            self.status_var.set(f"Terminal error: {exc}")
            return "break"

        if completed.stdout:
            self._append_terminal_output(completed.stdout if completed.stdout.endswith("\n") else f"{completed.stdout}\n")
        if completed.stderr:
            self._append_terminal_output(completed.stderr if completed.stderr.endswith("\n") else f"{completed.stderr}\n")
        self._append_terminal_output(f"[exit {completed.returncode}]\n")
        self.terminal_input.delete(0, tk.END)
        self.status_var.set(f"Terminal exit code: {completed.returncode}")
        self._refresh_pane(self.left, keep_selection=True)
        self._refresh_pane(self.right, keep_selection=True)
        return "break"


def main() -> None:
    root = tk.Tk()
    TwoPaneCommander(root)
    root.mainloop()


if __name__ == "__main__":
    main()
