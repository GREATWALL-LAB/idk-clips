"""Moved: rendering lives in ``app.jobs.compute`` (shared with paired workers).

This module only keeps the old import path working.
"""

from app.jobs.compute import auto_frame_position, render

__all__ = ["auto_frame_position", "render"]
