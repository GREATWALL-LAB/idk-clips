#!/usr/bin/env bash
# Check that this computer has everything IDK Clips needs (read-only).
set -euo pipefail
cd "$(dirname "$0")/../../backend"
if [[ ! -x .venv/bin/python ]]; then
  echo "IDK Clips is not set up yet. Run: bash scripts/linux/setup.sh"
  exit 1
fi
exec .venv/bin/python -m app doctor
