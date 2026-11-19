# Architecture

## Overview

```
                ┌───────────────────────────── browser ─────────────────────────────┐
                │  Web interface (Next.js static export: HTML, CSS, JavaScript)     │
                └──────────────┬──────────────────────────────────┬─────────────────┘
                     REST + session cookie               hybrid mode only:
                               │                         video files over 127.0.0.1
                ┌──────────────▼──────────────┐         ┌──────────▼──────────────────┐
                │  FastAPI API (backend/app)  │◄────────┤  Worker agent (app.agent)   │
                │  accounts, projects, jobs,  │  HTTPS  │  on the user's computer:    │
                │  events, workers, metadata  │ (worker │  bridge on 127.0.0.1,       │
                └──────────────┬──────────────┘ polls)  │  FFmpeg, faster-whisper,    │
                               │                         │  Ollama, local file storage │
                     PostgreSQL / SQLite                 └─────────────────────────────┘
```

| Component | Location | Technology |
|---|---|---|
| Web interface | `frontend/` | Next.js 16 (App Router, static export), React 19, TypeScript, Tailwind CSS 4, Motion |
| API | `backend/app/` | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Job pipeline | `backend/app/jobs/` | Shared by every mode |
| Worker agent | `backend/app/agent/` | httpx client, uvicorn bridge |
| Media library | `processing/openclip_processing/` | FFmpeg/FFprobe, faster-whisper, Ollama/OpenAI-compatible APIs, libass captions, NumPy framing |

## Run modes

| | `local` | `server` | `hybrid` |
|---|---|---|---|
| Accounts | One implicit user | Yes | Yes |
| Who processes | This process | This server (thread or Celery) | Each user's paired worker |
| Where videos live | Local `data/storage` | Server `data/storage` | The user's worker |
| Network exposure | Loopback only | Behind TLS | Behind TLS |

`OPENCLIP_MODE` selects the mode. The code path is the same; the differences are the
user dependency (`app/api/deps.py`), the job runner (`app/workers/runner.py`) and whether
the storage object holds bytes or only keys (`LocalStorage(remote=True)`).

## The job pipeline

Every job (import, transcribe, process, detect clips, render, purge files) goes through
three steps:

1. **Spec** (`jobs/specs.py`, server): a self-contained JSON description built from the
   database. Files are named by storage key, never by path. Nothing in a spec is code.
2. **Compute** (`jobs/compute.py`, anywhere): the actual work. It reads a spec, works in a
   storage folder, reports progress, and emits **events**. It never touches the database,
   so the same function runs in the API process and on a worker.
3. **Events** (`jobs/events.py`, server): every event is validated against a strict
   schema and applied only to the job's own project or clip. Storage keys must sit inside
   that project's folder.

`jobs/lifecycle.py` finishes a job and restores a sensible project/clip state when a job
fails or is cancelled.

In local and server mode, `workers/executor.py` runs spec → compute → events in-process.
In hybrid mode the worker claims a spec over HTTPS, runs compute locally and sends the
events back to `/api/v1/agent/jobs/{id}/events`.

## Hybrid coordination

- **Pairing** (`services/workers.py`): a signed-in user creates a one-time code (hashed,
  10 minutes). The worker exchanges it for its own bearer token (hashed on the server).
- **Claiming**: workers long-poll `POST /agent/jobs/claim`. The server atomically moves
  the oldest queued job of the worker's owner to `running` and gives it a **lease**
  (90 seconds), renewed by every progress report. A project's jobs are pinned to the
  worker that holds its files.
- **Recovery**: a maintenance task returns jobs with expired leases to the queue and fails
  them after three attempts. A worker that comes back within its lease window reclaims
  its job transparently. Workers retry with exponential backoff and deliver final results
  with retries.
- **Direct transfer**: the browser gets a short-lived transfer token from the API and
  talks to the worker's bridge on `127.0.0.1`. The bridge checks every token with the
  server and caches valid ones until they expire.
- **Deletion**: deleting a project or clip queues a `purge_files` job for the worker.

Polling was chosen over WebSockets or a message broker because it works through every
firewall and on small, inexpensive hosting with nothing but HTTPS.

## Data model

`users`, `auth_sessions`, `projects`, `transcripts` (segments and words as JSON), `clips`,
`jobs`, `workers`, `pairing_codes`, `transfer_tokens`, `app_settings`. Every user-owned row
carries the owner's ID, and every query filters on it. Migrations are in
`backend/alembic/versions/` and run at start-up.

## Clip detection

The AI model never writes timestamps. It receives numbered transcript segments and
returns the IDs of the first and last segment of each clip, a title, a description, a
reason and a rough interest score (labelled as an estimate in the UI). The backend fits
each range to the requested length at sentence boundaries, pads it slightly so words are
not cut, removes overlaps and returns at most the requested number. Fewer good moments
mean fewer clips; nothing is invented.

## Rendering and aspect ratios

`processing/openclip_processing/render.py` builds one FFmpeg filter graph per export:

- **Crop**: the largest window with the target ratio is cut from the source and moved
  along the cropped axis. `framing.py` can pick the position automatically by sampling
  frames and scoring detail and motion (the speaker usually moves).
- **Fit**: the whole picture, scaled without distortion, over a blurred copy.
- Output sizes: 1080×1920 (9:16), 1080×1350 (4:5), 1080×1080 (1:1), 1920×1080 (16:9), with
  square pixels.
- Captions are ASS subtitles rendered by libass with bundled fonts, sized relative to
  the frame's short side so they look the same in every ratio.

## Web interface

A static export, so one build runs on any static host and is also served by the API in
local mode. Data is fetched in the browser. Project and clip pages take their IDs from
the query string (`/projects/view/?id=…`), which static exports require.

## Decisions

| Decision | Reason |
|---|---|
| Keep the existing FastAPI backend and processing library | They worked and were tested; the new modes extend them. |
| Built-in accounts with Argon2id instead of a hosted auth service | Self-hosting needs no third-party account; a trusted, standard hashing library is used. The database can still be a hosted PostgreSQL such as Supabase. |
| Hybrid mode with user-owned workers | No GPU servers and no central video storage, so the service can stay free. |
| Long polling and leases | Works on cheap hosting, through firewalls, and survives disconnections. |
| Spec / compute / events split | One processing implementation for all modes; untrusted worker output is validated in one place. |
| Static export for the web interface | Free static hosting, and no Node.js needed at runtime for local users. |
| No YouTube downloading | YouTube's terms and technical protections; see [YOUTUBE.md](YOUTUBE.md). |
| No Redis requirement | The built-in job thread is enough for one machine; Celery stays optional for server mode. |
