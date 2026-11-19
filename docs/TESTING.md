# Testing

## Running the tests

```bash
# Backend: API, auth, authorization, workers, pipeline, exports
cd backend
.venv/Scripts/python -m pytest -q                 # Linux/macOS: .venv/bin/python

# Processing library: FFmpeg helpers, captions, rendering, framing, clip detection
cd ../processing
../backend/.venv/Scripts/python -m pytest -q

# Web interface: unit and component tests (Vitest + Testing Library + jsdom)
cd ../frontend
npm test
npm run lint && npm run typecheck && npm run build
```

Tests that need FFmpeg find it in `tools/ffmpeg/bin` or on `PATH` and **skip themselves**
when it is missing. Every test gets its own temporary database and data folder.

## What is covered

| Area | Where |
|---|---|
| Registration, sign-in, sessions, password rules, throttling | `backend/tests/test_auth.py` |
| Users cannot see or change each other's projects, clips, jobs, workers | `test_projects.py`, `test_clips.py`, `test_workers.py`, `test_youtube.py` |
| Upload validation (type, size, empty, no audio, damaged files) | `test_projects.py`, `test_agent.py` |
| Path traversal and storage keys | `test_storage_and_files.py`, `test_workers.py`, `test_agent.py` |
| URL import SSRF protection | `test_url_import.py` |
| CORS, CSRF, rate limits, error format | `test_cors.py`, `test_rate_limit.py`, `test_errors.py` |
| Local mode: no account, loopback only, DNS rebinding, web interface serving | `test_local_mode.py` |
| Worker pairing, one-time codes, revocation, rate limits | `test_workers.py` |
| Job assignment to the right worker, leases, disconnections, retries | `test_workers.py`, `test_agent.py` |
| Worker bridge: loopback only, CORS, transfer tokens | `test_agent.py` |
| Real upload → render → download through a worker | `test_agent.py::test_agent_processes_a_real_video_end_to_end` |
| All four aspect ratios × crop/fit export at the exact size | `test_agent.py::test_every_aspect_ratio_is_exported_at_its_real_size` |
| Per-clip aspect ratio through the server pipeline | `test_account.py` |
| Retention and deleting data/accounts | `test_account.py` |
| YouTube link parsing and the official oEmbed lookup | `test_youtube.py` |
| Captions, rendering, framing, clip detection logic | `processing/tests/` |
| Front-end helpers, ratio math, bridge URLs, homepage and dialogs | `frontend/src/**/*.test.ts(x)` |

## Integration tests with real AI

Two tests use real models and are skipped unless they are available:

- `test_pipeline_transcription.py`: transcribes the sample video with faster-whisper.
- `test_pipeline_full.py`: upload → transcription → clip detection with a real Ollama
  model → export → checks the MP4.

Create the sample video (original text-to-speech content, no third-party media) with
`scripts\windows\make-sample-video.cmd`, start Ollama with at least one chat model, then:

```bash
.venv/Scripts/python -m pytest -m integration -s
```

## Security checks

```bash
backend/.venv/Scripts/python scripts/predeploy_check.py           # everything below, plus builds
backend/.venv/Scripts/python scripts/predeploy_check.py --quick   # only file and secret checks
```

It checks that no `.env` files, keys, databases or media are among the files to publish,
scans those files with `detect-secrets` (findings reviewed as harmless placeholders are
listed in `.secrets.baseline`; anything new fails), and runs `ruff`, all test suites,
`pip-audit`, `npm audit` and the production build. It never pushes or deploys anything.

## Manual checks

Responsive layouts and the scroll animations are checked in a browser at phone (375 px),
tablet (768 px) and desktop widths, with and without "reduce motion".
