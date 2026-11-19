# Configuration

IDK Clips is configured with environment variables. They keep the `OPENCLIP_` prefix
from the project's earlier name, so existing configurations keep working. For a local installation, copy
`.env.example` (project root) to `.env` and change what you need. Real environment
variables win over the file. **Never commit `.env`**; it is ignored by `.gitignore`.

The web interface has a few build-time settings of its own; see
[Web interface settings](#web-interface-settings).

## Run mode

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_MODE` | `local` | `local`: one user, no account, this computer only. `server`: accounts, processing on this server. `hybrid`: accounts, processing on each user's paired worker; the server stores no video. |
| `OPENCLIP_HOST` / `OPENCLIP_PORT` | `127.0.0.1` / `8000` | Where the API listens. Local mode refuses non-loopback hosts. |
| `OPENCLIP_ENVIRONMENT` | `development` | `production` turns on secure cookies and hides `/api/docs`. |
| `OPENCLIP_PUBLIC_API_URL` | – | Public address of the API (shown in worker pairing commands). |
| `OPENCLIP_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Web origins allowed to call the API (and, in hybrid mode, workers' bridges). No wildcards. |
| `OPENCLIP_LOCAL_ALLOW_REMOTE` | `false` | Local mode only: accept non-loopback peers. Only for a Docker port published on `127.0.0.1`. |
| `OPENCLIP_WEB_DIST_DIR` | `frontend/out` | Exported web interface served by the API, if present. |

## Accounts and security

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_ALLOW_REGISTRATION` | `true` | Allow public sign-ups. Every account is an ordinary user; IDK Clips has no administrator role. |
| `OPENCLIP_EMAIL_VERIFICATION` | `supabase` | New accounts must verify their email address with a one-time code sent through Supabase Auth before they can be used. `off` is only for development and tests; production refuses it. |
| `OPENCLIP_SUPABASE_URL` | – | Supabase project URL (`https://<ref>.supabase.co`). Without it, sign-ups stay closed while verification is on. |
| `OPENCLIP_SUPABASE_ANON_KEY` | – | The project's public anon (publishable) key. Never the service-role key. |
| `OPENCLIP_EMAIL_OTP_TTL_MINUTES` | `10` | How long a code is valid. Set Supabase's "Email OTP Expiration" to the same value (in seconds). |
| `OPENCLIP_EMAIL_OTP_RESEND_SECONDS` | `60` | Wait before another code can be requested. |
| `OPENCLIP_EMAIL_OTP_MAX_ATTEMPTS` | `5` | Wrong codes allowed before a new code is needed. |
| `OPENCLIP_REGISTER_RATE_LIMIT_PER_HOUR` | `5` | New accounts per client address per hour. |
| `OPENCLIP_FAILED_REQUEST_LIMIT_PER_MINUTE` | `60` | 401/403/404 answers per client address per minute before it is slowed down. |
| `OPENCLIP_MAX_ACTIVE_JOBS_PER_USER` | `10` | Queued plus running jobs per user (0 = no limit). |
| `OPENCLIP_DAILY_PROCESSING_MINUTES_PER_USER` | `0` | Minutes of video per user per 24 hours (0 = no limit). |
| `OPENCLIP_MAX_REQUEST_BODY_MB` / `OPENCLIP_MAX_WORKER_PAYLOAD_MB` | `2` / `32` | Largest request bodies (video uploads have their own limit). |
| `OPENCLIP_CLIENT_IP_HEADER` | – | Header with the real client address behind a proxy that overwrites it (`x-real-ip` on Vercel). Leave unset otherwise. |
| `OPENCLIP_SERVERLESS` / `OPENCLIP_DATABASE_URL_ENV` | `false` / – | Serverless hosting (hybrid mode with PostgreSQL), and the name of the host's database variable, for example `DATABASE_URL`. |

**Age confirmation.** Every account answers "Are you 18 years of age or older?" before
it can be created (the server requires an explicit `true`; nothing is assumed), and the
time of the answer is stored. Accounts created before this rule existed answer once at
their next login. Without a Yes there is no account and no access.
| `OPENCLIP_SESSION_DAYS` | `14` | Session lifetime. |
| `OPENCLIP_COOKIE_SECURE` | auto | Secure cookies; on by default in production. |
| `OPENCLIP_RATE_LIMIT_ENABLED` | `true` | Request rate limiting. |
| `OPENCLIP_RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | General per-client budget. |
| `OPENCLIP_LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Sign-in attempts per client. |
| `OPENCLIP_UPLOAD_RATE_LIMIT_PER_HOUR` / `OPENCLIP_JOB_RATE_LIMIT_PER_HOUR` | `30` / `120` | Per-user limits for uploads and processing requests. |

## Storage, database and limits

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_DATA_DIR` | `data` | Database (SQLite), files, models and temporary files. |
| `OPENCLIP_DATABASE_URL` | SQLite in the data folder | For example `postgresql+psycopg://user:password@host:5432/openclip`. |
| `OPENCLIP_MAX_UPLOAD_MB` | `4096` | Largest accepted video. |
| `OPENCLIP_MAX_VIDEO_MINUTES` | `240` | Longest accepted video. |
| `OPENCLIP_USER_STORAGE_QUOTA_MB` | `0` (unlimited) | Per-user storage quota (server mode). |
| `OPENCLIP_DEFAULT_RETENTION_DAYS` | `0` (keep) | Delete source videos after this many days unless a user sets their own value. |
| `OPENCLIP_URL_IMPORT_ENABLED` | `true` | Allow imports from direct video links (private network addresses are always blocked unless `OPENCLIP_URL_IMPORT_ALLOW_PRIVATE_NETWORKS=true`). |
| `OPENCLIP_YOUTUBE_LOOKUP_ENABLED` | `true` | Look up public titles of YouTube links through YouTube's oEmbed API. |

## Transcription (faster-whisper)

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_WHISPER_DEFAULT_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, `large-v3`, or the English-only `.en` variants. Bigger is more accurate and slower. |
| `OPENCLIP_WHISPER_DEVICE` | `auto` | `auto` uses an NVIDIA GPU when CUDA works, otherwise the CPU. `cpu` or `cuda` to force one. |
| `OPENCLIP_WHISPER_COMPUTE_TYPE` | `auto` | `float16` on GPU, `int8` on CPU by default. |
| `OPENCLIP_MODELS_PATH` | `data/models` | Where speech models are cached. |

Models are downloaded from Hugging Face (the `Systran/faster-whisper-*` repositories) the
first time they are used. Rough sizes: tiny 75 MB, base 145 MB, small 484 MB, medium
1.5 GB, large-v3 3 GB. As a starting point: `small` on a CPU, `large-v3-turbo` on a GPU
with 6 GB or more.

## AI clip detection (Ollama and external providers)

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint. |
| `OPENCLIP_OLLAMA_MODEL` | first installed chat model | Model used for clip detection (changeable in Settings → AI). |
| `OPENCLIP_OLLAMA_TIMEOUT_SECONDS` / `OPENCLIP_OLLAMA_NUM_CTX` | `600` / `8192` | Answer timeout and context window. |
| `OPENCLIP_EXTERNAL_AI_BASE_URL` / `_MODEL` / `_API_KEY` / `_NAME` | – | Any OpenAI-compatible chat API. Keys stay on the server and are never sent to browsers. |
| `OPENCLIP_AGENT_AI_PROVIDER` | `ollama` | On a worker: `ollama` or `external` (using the worker's own external settings). |

**Setting up Ollama**: install it from [ollama.com](https://ollama.com), make sure it runs
(the Ollama app, or `ollama serve`), then download a model. Models with structured
output support work best. Examples by GPU memory: `gemma3:4b` or `qwen2.5:3b` (4–6 GB),
`qwen2.5:7b` or `llama3.1:8b` (8 GB), `gemma3:12b` (12 GB+). On a CPU, use a small model
and expect several minutes per hour of video.

## Video export (FFmpeg)

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_FFMPEG_PATH` / `OPENCLIP_FFPROBE_PATH` | auto | Explicit paths. Otherwise `tools/ffmpeg/bin` and then `PATH` are searched. |
| `OPENCLIP_VIDEO_ENCODER` | `auto` | `auto` uses NVIDIA NVENC when a quick test encode works, otherwise `libx264`. |

**Installing FFmpeg**: Windows `scripts\windows\install-ffmpeg.cmd` (portable copy,
checksum verified); Debian/Ubuntu `sudo apt install ffmpeg`; macOS `brew install ffmpeg`.
FFmpeg must include `libx264`, `libass` (captions) and the `aac` encoder, which the usual
builds do.

## Background jobs (server mode)

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_JOB_BACKEND` | `local` | `local`: one job at a time in the API process. `celery`: a separate Celery worker with Redis. Ignored in hybrid mode. |
| `OPENCLIP_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis for Celery. |

## Hybrid mode and workers

| Variable | Default | Meaning |
|---|---|---|
| `OPENCLIP_PAIRING_CODE_MINUTES` | `10` | How long a pairing code is valid. |
| `OPENCLIP_WORKER_LEASE_SECONDS` | `90` | A running job returns to the queue when its worker is silent this long. |
| `OPENCLIP_WORKER_JOB_MAX_ATTEMPTS` | `3` | After this many lost attempts a job is marked as failed. |
| `OPENCLIP_WORKER_LONG_POLL_SECONDS` | `20` | How long a worker's "any work?" request may wait. |
| `OPENCLIP_TRANSFER_TOKEN_MINUTES` | `30` | Lifetime of browser-to-worker transfer tokens. |
| `OPENCLIP_MAX_WORKERS_PER_USER` | `5` | Connected workers per account. |
| `OPENCLIP_AGENT_BRIDGE_PORT` | `8787` | On a worker: the local bridge port (loopback only). |
| `OPENCLIP_AGENT_ALLOW_HTTP` | `false` | On a worker: allow a plain-HTTP server that is not on this computer. |

## Logging

`OPENCLIP_LOG_LEVEL` (`INFO`) and `OPENCLIP_LOG_FORMAT` (`console` or `json`). Configured
secrets are redacted from every log line.

## Web interface settings

These are read when the web interface is **built** (`npm run build` in `frontend/`).
They end up in public JavaScript, so never put secrets in them.

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | same origin (dev: `http://localhost:8000`) | Where the browser reaches the API. Leave empty when the API serves the site itself. |
| `NEXT_PUBLIC_GITHUB_URL` | – | Public repository URL (https only). GitHub links stay hidden until it is set. |
| `NEXT_PUBLIC_SITE_URL` | – | Public address of the hosted website (https only). Used for canonical, Open Graph and social-card links. |
