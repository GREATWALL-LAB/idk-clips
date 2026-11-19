"""Errors raised by the processing library.

``user_message`` is written for end users and is safe to show in the UI.
``detail`` holds technical information (FFmpeg output, exception text) that is
only written to server logs.
"""

from __future__ import annotations


class ProcessingError(Exception):
    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class FFmpegNotFoundError(ProcessingError):
    pass


class FFmpegError(ProcessingError):
    pass


class MediaValidationError(ProcessingError):
    pass


class TranscriptionError(ProcessingError):
    pass


class AIProviderError(ProcessingError):
    pass


class ClipDetectionError(ProcessingError):
    pass


class JobCancelled(ProcessingError):
    def __init__(self) -> None:
        super().__init__("The job was cancelled.")
