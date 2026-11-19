"""The job pipeline shared by every run mode.

A job goes through three steps, each in its own module:

``specs``    The server turns a queued job into a self-contained *spec*: plain JSON
             built from the database. Nothing in a spec is executable.
``compute``  Pure processing (FFmpeg, transcription, AI). It reads a spec, works on
             files in a storage folder and reports *events*. It never touches the
             database, so the same code runs inside the API process (local and
             server mode) and on a user's paired worker (hybrid mode).
``events``   The server validates every event and applies it to the database. An
             event can only change the project or clip its job belongs to.

``lifecycle`` holds the bookkeeping around a job: starting, finishing and settling
the project state when a job fails or is cancelled.
"""

#: Every job type the pipeline knows. Anything else is rejected by servers and workers.
JOB_TYPES = (
    "import_url",
    "transcribe",
    "process",
    "detect_clips",
    "render_clip",
    "purge_files",
)
