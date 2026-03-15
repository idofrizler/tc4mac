# TC Mac Lite

A keyboard-first, two-pane file explorer for macOS inspired by classic commander-style workflows.

## Run

```bash
cd /Users/idofrizler/temp/tc-mac-lite
python3 app.py
```

## Core controls

- Main list columns: **Name**, **Size**, **Ext**, **Last Modified**
- Click a column header to sort by that column (click again to toggle ascending/descending)
- Double-click a **column separator** to auto-fit that column to content (only if enough width remains for other columns)
- `Tab` - switch active pane and move highlight to the opposite pane
- Double-click the **center pane separator** to reset it to middle
- `Up` / `Down` - move selection in active pane
- `Enter` / double click - open directory or file
- `Enter` also clears the current search text
- `Backspace` - edits search text while in search mode; outside search mode it goes to parent directory
- `Right Arrow` - open command terminal panel at the bottom
- `Esc` hides the command terminal panel
- Type any letters/numbers directly in a pane - live filter active pane list
- `*` in the typed filter works as wildcard
- `Space` - mark/unmark current file or directory (stays on the same row)
- Marked items are shown in **red**
- `F3` - view selected file (read-only)
- `F4` - edit selected file
- `Shift+F4` - create new file in current folder and open editor
- `F5` - copy selected/marked items to the other pane
- `F6` - move selected/marked items to the other pane
- F5/F6 now open a small operation dialog; for single-file copy/move, pressing F5/F6 again toggles name selection between **name-only** and **full filename** for quick rename
- `Shift+F6` - rename selected file/directory (TC-style rename shortcut)
- `F7` - create directory in active pane
- `F8` - delete selected/marked items
- `Esc` - exit search mode (or close terminal when terminal input is focused)
- `Ctrl+D` - open favorites hotlist window

## Notes

- If any items are marked with `Space`, file operations use the marked set.
- If nothing is marked, operations use the currently selected item.
- Typed search is shown in a small box at the bottom right (`Search: ...`).
- In the terminal panel, `Enter` runs the command in the active pane directory and `Esc` closes the panel.
- In favorites hotlist, use `Up/Down` and `Enter` to choose a folder; use **Add current** to save the active path.
- This is a practical starter implementation inspired by Total Commander behavior.
