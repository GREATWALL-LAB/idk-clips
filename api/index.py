"""Vercel entry point: the IDK Clips API as a serverless Python function.

The hosted website runs in hybrid mode: it keeps accounts, projects and job state in
PostgreSQL, while every user's own computer (a paired worker) stores and processes their
videos. This file only makes the backend importable and builds the FastAPI app; all
configuration comes from environment variables (see docs/DEPLOYMENT.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("backend", "processing"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from app.main import create_app  # noqa: E402

app = create_app()
