# IDK Clips

**Long videos in. Short clips out.** IDK Clips is a free, open-source tool that turns
long videos (talks, podcasts, lectures, interviews) into short clips. It transcribes the
speech, lets an AI model find the moments that stand on their own, adds captions and
exports MP4 files in **9:16, 4:5, 1:1 or 16:9**.

- **Free and MIT licensed.** No subscriptions, paid tiers, credits or watermarks.
- **Runs on your hardware.** Transcription (faster-whisper), AI analysis (Ollama) and
  rendering (FFmpeg) happen on your own computer.
- **Two ways to use it.** Run it locally with no account, or use the website while your
  own computer does the processing.

**Website:** https://idk-clips.vercel.app · **Docs:** https://idk-clips.vercel.app/docs/

## What it does

1. **Import** a video file (or reference your own YouTube video and add the original file).
2. **Transcribe** speech with word-level timestamps (faster-whisper, CPU or NVIDIA GPU).
3. **Find moments**: a local AI model reads the transcript and suggests 5–10 complete
   clips with a title and a reason. The model picks transcript segments; times always
   come from the real speech.
4. **Edit**: drag the start and end on a timeline with word snapping, rename clips,
   choose the aspect ratio per clip, style the captions and fix any word.
5. **Export** an MP4 (H.264 + AAC) at 1080×1920, 1080×1350, 1080×1080 or 1920×1080, with
   subject-aware cropping or a whole-picture fit. Nothing is ever stretched.

## Quick start (run locally)

You need **Python 3.11+**, **Node.js 20.9+**, **FFmpeg**, and optionally
[**Ollama**](https://ollama.com) with a model for AI clip suggestions.

Windows:

```bat
scripts\windows\install-ffmpeg.cmd   :: optional: portable FFmpeg in tools\ffmpeg
scripts\windows\setup.cmd            :: once: Python environment, packages, web build
scripts\windows\start.cmd            :: then open http://localhost:8000
```

Linux and macOS (scripts included, not yet verified by the maintainers):

```bash
bash scripts/linux/setup.sh
bash scripts/linux/start.sh          # then open http://localhost:8000
```

Check your setup at any time with `scripts\windows\doctor.cmd` or
`bash scripts/linux/doctor.sh`. Full guide: [docs/INSTALLATION.md](docs/INSTALLATION.md).

| Platform | Status |
|---|---|
| Windows 11 (x64, NVIDIA GPU) | Tested by the maintainers |
| Linux (x64) | Scripts provided, not yet verified |
| macOS (Apple silicon) | Scripts provided, not yet verified; CPU transcription only |

## Use online (hybrid mode)

An IDK Clips server can run in **hybrid mode**: people sign in on the website, and each
user connects their own computer as a **worker**. The website coordinates projects and
stores text (titles, transcripts, clip timings); the videos go from the browser straight
to the user's worker on the same computer, which does all the processing. See
[docs/USING_ONLINE.md](docs/USING_ONLINE.md) and [docs/WORKERS.md](docs/WORKERS.md).

Accounts are for people aged 18 or older (an explicit Yes at sign-up, stored with a
timestamp) and must verify their email address with a one-time code (Supabase Auth)
before they can be used; passwords can be reset the same way. There is no administrator
system: every account is an ordinary user who can reach only their own projects, clips
and data.

## Technology

| Part | Built with |
|---|---|
| Web interface | Next.js 16 (static export), React, TypeScript, Tailwind CSS |
| API | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Argon2id; SQLite or PostgreSQL |
| Processing | faster-whisper (speech), Ollama or an OpenAI-compatible model (moments), FFmpeg (rendering, captions) |
| Email codes | Supabase Auth (one-time codes) with any SMTP provider |
| Public website | Vercel (website + API as a Python function), Neon PostgreSQL, Supabase, Brevo; all on free plans |

## Automation

Every push and pull request runs lint, type checks, the backend, processing and web test
suites, a production build, an SEO and broken-link check, a secret scan and dependency
audits (`.github/workflows/ci.yml`). CodeQL, Dependabot, a daily security audit, an uptime
check and a deploy-to-Vercel workflow are included. Locally, the same checks run with
`backend/.venv/Scripts/python scripts/predeploy_check.py` (Linux: `.venv/bin/python`).

## Documentation

| Guide | |
|---|---|
| [Installation](docs/INSTALLATION.md) | Requirements, setup, requirements checker |
| [Run locally](docs/LOCAL_MODE.md) | No account, nothing uploaded |
| [Use online](docs/USING_ONLINE.md) · [Workers](docs/WORKERS.md) | Hybrid mode and device pairing |
| [Configuration](docs/CONFIGURATION.md) | All settings; FFmpeg, faster-whisper and Ollama setup |
| [YouTube videos](docs/YOUTUBE.md) | Why IDK Clips never downloads from YouTube |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [Self-hosting](docs/SELF_HOSTING.md) · [Deployment](docs/DEPLOYMENT.md) | Servers, Docker, low-cost hosting |
| [Architecture](docs/ARCHITECTURE.md) · [Testing](docs/TESTING.md) | How it works inside |
| [Privacy](docs/PRIVACY.md) · [Terms](docs/TERMS.md) · [Security](SECURITY.md) | |

## Repository layout

```
backend/      FastAPI API, job pipeline, worker agent (python -m app.agent), tests
processing/   Media library: FFmpeg, transcription, AI clip detection, captions, framing
frontend/     Next.js web interface (static export), served by the backend in local mode
scripts/      Setup and start scripts for Windows and Linux/macOS
docker/       Dockerfile and Compose files for self-hosting
deploy/       Example production configuration; Supabase email templates
api/          Vercel entry point for the hosted API (vercel.json, requirements.txt)
docs/         Documentation (also published on the website under /docs)
.github/      CI, CodeQL, scheduled audits, deploy and uptime workflows, templates
```

## Contributing

Contributions are welcome: code, translations, documentation, testing on Linux and macOS.
Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).
Report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). Bundled caption fonts (Montserrat, Poppins, Anton) are under the SIL Open
Font License; their license files are next to the fonts in
`processing/openclip_processing/assets/fonts/`.

Only process videos you own or have permission to use.
