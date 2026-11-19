#!/usr/bin/env bash
# Start IDK Clips in local mode (no account, this computer only) on http://localhost:8000
# For development with hot reload use scripts/linux/start-dev.sh instead.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ ! -x backend/.venv/bin/python ]]; then
  echo "IDK Clips is not set up yet. Run: bash scripts/linux/setup.sh"
  exit 1
fi
if [[ ! -f frontend/out/index.html ]]; then
  echo "The web interface has not been built yet. Run setup again, or: (cd frontend && npm run build)"
  exit 1
fi
echo "IDK Clips: open http://localhost:8000 in your browser. Press Ctrl+C to stop."
cd backend
exec .venv/bin/python -m app "$@"
