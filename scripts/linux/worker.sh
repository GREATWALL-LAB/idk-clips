#!/usr/bin/env bash
# IDK Clips worker: processes your videos on this computer for your online account.
#   bash scripts/linux/worker.sh pair --server https://api.example.com --code ABCD-EFGH
#   bash scripts/linux/worker.sh run
#   bash scripts/linux/worker.sh status | unpair | doctor | purge --yes
set -euo pipefail
cd "$(dirname "$0")/../../backend"
if [[ ! -x .venv/bin/python ]]; then
  echo "IDK Clips is not set up yet. Run: bash scripts/linux/setup.sh"
  exit 1
fi
exec .venv/bin/python -m app.agent "$@"
