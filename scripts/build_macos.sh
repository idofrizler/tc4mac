#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! python3 -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is required. Install it in a venv, then re-run:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && python -m pip install pyinstaller"
  exit 1
fi

python3 -m PyInstaller --noconfirm --clean tc4mac.spec
echo "Build complete: $ROOT_DIR/dist/TC4Mac.app"
