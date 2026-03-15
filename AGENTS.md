# TC4Mac Agent Handoff

This repository contains a single-file Tkinter desktop app (`app.py`) that implements a Total Commander-inspired dual-pane file manager on macOS.

## Current project state

- Main app: `app.py`
- User docs: `README.md`
- No test suite yet; validation command:
  - `python3 -m py_compile app.py`

## Core behavior already implemented

- Dual-pane explorer with active-pane focus and path entry
- Keyboard-first workflows:
  - `Tab`: switch pane
  - `Up` / `Down`: move row selection
  - `Enter`: open selected file/folder and clear active search mode
  - `Backspace`: parent directory (unless in search mode)
  - Type-to-search live filter (supports `*` wildcard), `Esc` exits search mode
  - `F3` view, `F4` edit, `Shift+F4` create new file
  - `F5` copy, `F6` move, `Shift+F6` rename
  - `F7` mkdir, `F8` delete
  - `Ctrl+D` favorites hotlist
  - `Right Arrow`: open bottom command panel
- Columns: Name / Size / Ext / Last Modified
- Sorting by clicking column headers (toggle asc/desc)
- Double-click column separator: auto-fit column width (bounded by available pane width)
- Double-click center sash: recenter left/right pane split

## Implementation notes

- UI technology: `tkinter` + `ttk.Treeview`
- Favorites persistence: `~/.tc-mac-lite-favorites.json`
- Marked items are tracked per pane and rendered in red (`marked` tag)
- Copy/move uses dialog-based target selection; single-item copy/move supports quick rename selection toggling

## Guidance for spawned agents

1. Preserve keyboard-driven behavior and TC-like ergonomics.
2. Keep changes surgical and in-style (single-file app unless refactor is requested).
3. Avoid breaking existing shortcuts; if reassigning keys, update `README.md`.
4. After changes, run:
   - `python3 -m py_compile app.py`
5. If behavior changes, document it in `README.md`.

