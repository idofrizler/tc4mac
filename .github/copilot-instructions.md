# Copilot Instructions for tc4mac

## Project summary

`tc4mac` is a macOS-oriented, Total Commander-inspired two-pane file manager implemented in Python Tkinter.

- Main code file: `app.py`
- User documentation: `README.md`
- Runtime: `python3 app.py`

## Expectations for changes

- Preserve existing shortcut semantics unless explicitly requested by the user.
- Keep UX keyboard-first and commander-style.
- Prefer minimal, targeted edits over broad rewrites.
- Maintain current visual behaviors:
  - Active pane indicator
  - Red-marked items
  - Search mode display

## Existing key flows (do not regress)

- Navigation: Tab, Up/Down, Enter, Backspace
- Search mode: type-to-filter with `*`, `Esc` exits search mode
- File ops: F3/F4/Shift+F4/F5/F6/Shift+F6/F7/F8
- Favorites: Ctrl+D hotlist
- Terminal panel: Right Arrow opens, Esc hides
- Column interactions: sortable headers + separator auto-fit
- Pane splitter: double-click sash centers panes

## Validation

After editing, run:

```bash
python3 -m py_compile app.py
```

Update `README.md` if any user-facing behavior or shortcuts change.

