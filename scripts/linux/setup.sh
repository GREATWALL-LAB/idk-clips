#!/usr/bin/env bash
# =====================================================================
#  IDK Clips - one-time setup for Linux and macOS
#  Creates a Python virtual environment (backend/.venv), installs the
#  frontend packages and builds the web interface. Nothing is installed
#  system-wide. Usage:  bash scripts/linux/setup.sh [--dev]
#
#  Status: written for Linux and macOS but not yet verified on them by the
#  maintainers. Reports and fixes are welcome (see CONTRIBUTING.md).
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

REQS="backend/requirements.txt"
if [[ "${1:-}" == "--dev" ]]; then REQS="backend/requirements-dev.txt"; fi

say() { printf '\n[IDK Clips] %s\n' "$*"; }

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Install it (for example: sudo apt install python3 python3-venv)."
  exit 1
fi
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "Python 3.11 or newer is required (found $("$PYTHON" --version))."
  exit 1
}
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 20.9+ was not found. Install the LTS version from https://nodejs.org/"
  exit 1
fi

if [[ ! -x backend/.venv/bin/python ]]; then
  say "Creating Python virtual environment in backend/.venv ..."
  "$PYTHON" -m venv backend/.venv
fi

say "Installing backend packages from $REQS ..."
backend/.venv/bin/python -m pip install --upgrade pip --disable-pip-version-check
backend/.venv/bin/python -m pip install -r "$REQS" --disable-pip-version-check
backend/.venv/bin/python -m pip install -e processing --disable-pip-version-check

say "Installing frontend packages and building the web interface ..."
(cd frontend && npm ci --no-fund --no-audit && npm run build)

if ! command -v ffmpeg >/dev/null 2>&1 && [[ ! -x tools/ffmpeg/bin/ffmpeg ]]; then
  say "FFmpeg was not found. Install it with your package manager, for example:"
  echo "    Debian/Ubuntu:  sudo apt install ffmpeg"
  echo "    Fedora:         sudo dnf install ffmpeg   (RPM Fusion)"
  echo "    macOS:          brew install ffmpeg"
fi

say "Checking the requirements ..."
(cd backend && .venv/bin/python -m app doctor) || true
say "Setup complete. Start IDK Clips with: bash scripts/linux/start.sh"
