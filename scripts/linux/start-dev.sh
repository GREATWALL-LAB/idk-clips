#!/usr/bin/env bash
# Development: backend with auto-reload plus the Next.js dev server. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/../.."
(cd backend && .venv/bin/python -m app --reload) &
BACKEND=$!
trap 'kill "$BACKEND" 2>/dev/null || true' EXIT INT TERM
echo "App: http://localhost:3000   API docs: http://localhost:8000/api/docs"
cd frontend && npm run dev
