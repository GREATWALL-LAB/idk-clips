# Contributing to IDK Clips

Thank you for helping. Every kind of contribution counts: bug reports, fixes, features,
documentation, translations and testing on platforms the maintainers do not use.

## Ground rules

- Be kind and constructive. The [code of conduct](CODE_OF_CONDUCT.md) applies everywhere.
- IDK Clips stays **free**. Changes that add paid tiers, usage limits, tracking or
  telemetry will not be accepted.
- Never commit secrets, real user videos, databases or model files. `.gitignore` excludes
  them; double-check before opening a pull request.
- Do not add code that downloads from YouTube or other platforms, or that bypasses DRM,
  sign-in or other technical protections. See [docs/YOUTUBE.md](docs/YOUTUBE.md).
- Report security issues privately ([SECURITY.md](SECURITY.md)), not in public issues.

## Development setup

```bash
# Windows                                  # Linux / macOS
scripts\windows\setup.cmd --dev            bash scripts/linux/setup.sh --dev
scripts\windows\start-dev.cmd              bash scripts/linux/start-dev.sh
```

`start-dev` runs the backend with auto-reload on http://localhost:8000 and the Next.js
dev server on http://localhost:3000. API documentation: http://localhost:8000/api/docs.

## Project structure

| Folder | What lives there |
|---|---|
| `processing/openclip_processing/` | Pure media code: FFmpeg, transcription, clip detection, captions, framing. No web or database code. |
| `backend/app/jobs/` | The job pipeline: `specs` (from the database), `compute` (the work), `events` (validated results). |
| `backend/app/api/v1/` | REST endpoints. `agent.py` is the worker protocol. |
| `backend/app/agent/` | The worker program (`python -m app.agent`). |
| `frontend/src/` | Next.js App Router pages and components. |

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before larger changes.

## Before you open a pull request

Run the same checks the maintainers run:

```bash
cd backend
.venv/Scripts/python -m ruff check app tests        # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m ruff format --check app tests
.venv/Scripts/python -m pytest -q
cd ../processing && ../backend/.venv/Scripts/python -m pytest -q
cd ../frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Tests that need FFmpeg skip themselves when it is missing; the full pipeline test also
needs Ollama with a model (see [docs/TESTING.md](docs/TESTING.md)). Mention in the pull
request which checks you ran and on which operating system.

## Style

- Python: type hints, `ruff` formatting (line length 100), user-facing error messages that
  say what to do next. Never put file paths, secrets or stack traces in API responses.
- TypeScript: strict mode, components in `src/components`, API calls only through
  `src/lib/api`. Use the design tokens in `src/app/globals.css` (no ad-hoc colours).
- Accessibility: every control needs a label, keyboard support and visible focus.
- Keep the UI honest: show real progress, label estimates as estimates, and never show
  invented numbers.

## Commit messages and pull requests

Write a short summary line in the imperative ("Add 4:5 preset to the editor"), then
explain the why. Keep pull requests focused; split unrelated changes. Database changes
need an Alembic migration in `backend/alembic/versions/`.

## Licensing

By contributing you agree that your contribution is released under the MIT License.
