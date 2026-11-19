"""Moved: clip detection is the second half of ``app.jobs.compute.analysis``.

Storing the suggestions is done by ``app.jobs.events``. This module only keeps the
old import path working.
"""

from app.jobs.compute import analysis
from app.jobs.events import untouched_ai_suggestion

__all__ = ["analysis", "untouched_ai_suggestion"]
