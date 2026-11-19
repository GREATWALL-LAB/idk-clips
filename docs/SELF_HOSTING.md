# Self-hosting

Run IDK Clips for yourself, a team or a community. Pick the mode first:

| Mode | Who processes | Server needs | Good for |
|---|---|---|---|
| `server` | The server | FFmpeg, enough CPU/GPU and disk for everyone's videos | A team with one strong machine |
| `hybrid` | Each user's own computer (worker) | Very little: no video storage, no GPU | A public or community site on cheap hosting |

`local` mode is for one person on one computer and is not meant to be exposed.

## Option 1: Docker Compose (server mode)

`docker/docker-compose.yml` runs the API with the built web interface, PostgreSQL and
optionally Ollama. It is provided for convenience and **has not been tested by the
maintainers yet** (Docker was not available in the development environment).

```bash
cp deploy/server.env.example deploy/server.env   # then edit: passwords, origins
docker compose -f docker/docker-compose.yml --env-file deploy/server.env up -d --build
```

The site is then served on port 8000 of the host. Put a TLS reverse proxy in front of it
for anything beyond your own network (see [deployment](DEPLOYMENT.md#tls-reverse-proxy)).

## Option 2: Directly on a machine

```bash
bash scripts/linux/setup.sh
cp .env.example .env
# edit .env:
#   OPENCLIP_MODE=server            (or hybrid)
#   OPENCLIP_ENVIRONMENT=production
#   OPENCLIP_HOST=127.0.0.1         (behind a reverse proxy)
#   OPENCLIP_DATABASE_URL=postgresql+psycopg://openclip:<password>@127.0.0.1:5432/openclip
#   OPENCLIP_CORS_ORIGINS=https://clips.example.com
bash scripts/linux/start.sh
```

The API serves the web interface from `frontend/out` at the same address, so one domain
is enough. Database migrations run automatically at start-up.

Run it as a service (systemd example):

```ini
[Unit]
Description=IDK Clips
After=network-online.target

[Service]
WorkingDirectory=/opt/openclip/backend
ExecStart=/opt/openclip/backend/.venv/bin/python -m app
Restart=on-failure
User=openclip

[Install]
WantedBy=multi-user.target
```

## Running the server (no administrator role)

IDK Clips has **no administrator system**: no admin accounts, roles, dashboard, API or
command. Every account is an ordinary user who can reach only their own projects,
clips, workers and data. Server-wide behaviour is set by whoever runs the server, in its
environment variables (see [configuration](CONFIGURATION.md)):

- The AI endpoint (`OPENCLIP_OLLAMA_BASE_URL`) and any external provider
  (`OPENCLIP_EXTERNAL_AI_*`) are fixed by the server. Each user picks their own provider
  and model in Settings; the choice affects only their projects.
- Upgrading from a version that had administrators removes the role (migration 0004);
  all accounts and their data stay.
- Close sign-ups with `OPENCLIP_ALLOW_REGISTRATION=false`.
- Limits: `OPENCLIP_MAX_UPLOAD_MB`, `OPENCLIP_MAX_VIDEO_MINUTES`,
  `OPENCLIP_USER_STORAGE_QUOTA_MB`, `OPENCLIP_DEFAULT_RETENTION_DAYS`.
- Health checks: `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready`
  (database and storage).

## Backups

Back up the database (PostgreSQL: `pg_dump`; SQLite: copy `data/openclip.db` while the
app is stopped) and, in server mode, the `data/storage/` folder. In hybrid mode the
server holds no videos; each user's files are on their own worker.

## Updating

Stop the app, update the code, run the setup script again (it reinstalls packages and
rebuilds the web interface), start the app. Migrations are applied automatically.
