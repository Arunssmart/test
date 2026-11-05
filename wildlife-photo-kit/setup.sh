#!/bin/bash
# One-time setup on a Mac: makes a private Python environment in .venv and checks the kit works.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "Python 3.9 or newer is needed."
  echo "Install it from https://www.python.org/downloads/macos/ (or run: xcode-select --install), then run ./setup.sh again."
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

# Optional extras: RAW files (NEF, CR2, ARW, DNG, ...) and iPhone HEIC photos.
.venv/bin/python -m pip install --quiet rawpy || echo "Note: RAW support (rawpy) could not be installed; RAW files will be skipped."
.venv/bin/python -m pip install --quiet pillow-heif || echo "Note: HEIC support (pillow-heif) could not be installed; HEIC files will be skipped."

.venv/bin/python kit.py selftest
echo
echo "Setup finished. Run steps with: .venv/bin/python kit.py <step> --help"
