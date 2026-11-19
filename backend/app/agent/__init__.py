"""The IDK Clips worker: runs on a user's own computer in hybrid mode.

The worker is paired to one account with a one-time code. After that it:

- keeps an outbound HTTPS connection pattern to the server (long polling); the
  server never connects to the worker, so no ports need to be opened;
- claims only its owner's jobs and runs them with the same processing code as
  local mode (``app.jobs.compute``): FFmpeg, faster-whisper and Ollama, locally;
- sends back text results (transcript, clip suggestions, status). Video files
  never leave the computer;
- runs a small *bridge* on 127.0.0.1 so the owner's browser can hand it a video
  and play or download the results directly.

It cannot be told to run commands: it understands a fixed list of job types and
validates every value before using it.

Run it with ``python -m app.agent`` (see ``--help``).
"""

AGENT_NAME = "openclip-worker"  # protocol identifier (User-Agent, bridge hello); not shown
DISPLAY_NAME = "IDK Clips worker"
