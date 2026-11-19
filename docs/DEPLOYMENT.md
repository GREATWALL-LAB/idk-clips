# Deployment and hosting

This is the plan for running the public IDK Clips website on a small budget, and the
exact steps to deploy it. **Nothing here has been deployed yet**; deploying requires the
owner's explicit approval.

## The live website (Vercel)

The public site **https://idk-clips.vercel.app** runs as one Vercel project: the static
web interface plus the API as a Python function under `/api` (`api/index.py`,
`vercel.json`), in hybrid mode with a free Neon PostgreSQL database attached through the
Vercel Marketplace. Users' own computers do all video work, so the function needs only the
slim packages in the root `requirements.txt`.

Production settings (Vercel > Project > Settings > Environment Variables):
`OPENCLIP_MODE=hybrid`, `OPENCLIP_ENVIRONMENT=production`, `OPENCLIP_SERVERLESS=true`,
`OPENCLIP_DATABASE_URL_ENV=DATABASE_URL` (set by the Neon integration),
`OPENCLIP_DATA_DIR=/tmp/idk-clips`, `OPENCLIP_CLIENT_IP_HEADER=x-real-ip`,
`OPENCLIP_CORS_ORIGINS`, `OPENCLIP_PUBLIC_APP_URL` and `OPENCLIP_PUBLIC_API_URL` (the site
address), `NEXT_PUBLIC_SITE_URL` (the same), and for sign-ups `OPENCLIP_SUPABASE_URL` and
`OPENCLIP_SUPABASE_ANON_KEY`.

### Email verification with Supabase

1. Create a Supabase project (free plan), directly or from the Vercel Marketplace.
2. Authentication > Sign In / Providers > Email: keep Email enabled, set **Email OTP
   Expiration** to `600` seconds (matching `OPENCLIP_EMAIL_OTP_TTL_MINUTES=10`) and the
   OTP length to 6.
3. Authentication > Emails > Templates: in **Magic Link** and **Confirm signup**, show the
   code with `{{ .Token }}`, for example "Your IDK Clips code is {{ .Token }}. It expires in
   10 minutes." (Without `{{ .Token }}` people receive a link instead of a code.)
4. Authentication > Emails > SMTP Settings: connect an email provider. Supabase's built-in
   sender only delivers to members of your Supabase organization and only a few messages
   per hour, so it is not enough for a public site.
5. Copy the Project URL and the anon / publishable key (Project Settings > API Keys) into
   `OPENCLIP_SUPABASE_URL` and `OPENCLIP_SUPABASE_ANON_KEY`, then redeploy. Never use the
   service-role key.

Until steps 1-5 are done, the site refuses new accounts with a clear message instead of
creating unverified ones.

## The plan in one table

| Part | Recommended | Cost | Why |
|---|---|---|---|
| Web interface (static files) | Cloudflare Pages, Free plan | $0 | Static export; unlimited bandwidth and static requests on Free; no non-commercial-only rule like Vercel Hobby (confirm in Cloudflare's current terms) |
| API (FastAPI, hybrid mode) | One small always-on container or VPS | about $4–7/month | Workers hold a connection open; free container tiers sleep or exclude production use |
| Database (PostgreSQL) | Supabase, Free plan | $0 to start | 500 MB is enough for text-only data at small scale |
| Video storage | None | $0 | In hybrid mode videos stay on users' own computers |
| GPU | None | $0 | All AI and video work runs on users' workers |

The design keeps every part replaceable: the web interface is plain files, the API is a
standard Docker image, and the database is plain PostgreSQL reached through
`OPENCLIP_DATABASE_URL`.

## Free-tier facts (checked 2026-11-17)

Free tiers change. Check the providers' pages before relying on these numbers.

- **Cloudflare Pages Free**: 500 builds per month, one build at a time, 20-minute build
  timeout, up to 20,000 files per site and 25 MiB per file, unlimited static requests and
  bandwidth. ([limits](https://developers.cloudflare.com/pages/platform/limits/))
- **Supabase Free**: 500 MB database per project, 5 GB egress (plus 5 GB cached), 1 GB file
  storage, 2 active projects; **projects are paused after one week of inactivity** and
  must be restored by hand. ([pricing](https://supabase.com/pricing))
- **Render Free web services**: spin down after 15 minutes without traffic, 750 instance
  hours per workspace and month, may restart at any time, and Render says not to use them
  for production. Fine for a test deployment, not for the public site.
  ([docs](https://render.com/docs/free))
- **Koyeb Free**: one instance with 0.1 vCPU and 512 MB, scales to zero after an hour
  without traffic. Too small for comfortable password hashing and long polling.
  ([instances](https://www.koyeb.com/docs/reference/instances))
- **Neon Free**: 100 compute-hours per project and month, 1 GB storage. Workers poll
  continuously, which keeps compute awake and would exhaust the hours.
  ([plans](https://neon.com/docs/introduction/plans))
- **Vercel Hobby**: limited to non-commercial personal use, so it is not used for the
  public site. ([fair use](https://vercel.com/docs/limits/fair-use-guidelines))
- **Cloudflare R2**: 10 GB-month storage, 1 million Class A and 10 million Class B
  operations per month free, no egress fees. Not needed today (no central video storage);
  noted for a possible future relay option. ([pricing](https://developers.cloudflare.com/r2/pricing/))

## What happens when limits are reached

| Limit | Effect | What to do |
|---|---|---|
| Supabase 500 MB | Writes start failing (new transcripts cannot be saved) | Transcripts with word timings take roughly 1 MB per hour of speech. Set `OPENCLIP_DEFAULT_RETENTION_DAYS`, ask users to delete old projects, or move to a paid database. |
| Supabase inactivity pause | The API cannot reach the database | Any daily use keeps it active; otherwise restore the project in the Supabase dashboard. |
| Cloudflare Pages builds | No new deployments until next month | Deploy on release tags instead of every commit. |
| API host CPU/RAM | Slow responses during busy times | Scale the container up; the API is stateless apart from the database. |
| Many workers | Each connected worker makes about 3 requests per minute | One small instance handles hundreds of workers; add instances behind a load balancer when needed (see "Scaling"). |

IDK Clips never promises unlimited storage or processing: in hybrid mode, processing
and storage are limited only by each user's own computer.

## Domains and cookies

Use two subdomains of one domain, for example `app.example.com` (web) and
`api.example.com` (API). They are the **same site**, so the `SameSite=Lax` session cookie
works. Configure:

- API: `OPENCLIP_CORS_ORIGINS=https://app.example.com`,
  `OPENCLIP_PUBLIC_API_URL=https://api.example.com`
- Web build: `NEXT_PUBLIC_API_URL=https://api.example.com`

## Step 1: database (Supabase)

1. Create a project; choose a region close to the API host; set a strong database
   password and keep it in a password manager.
2. Copy the **direct connection** string (or the session pooler for IPv4 networks) and turn
   it into an SQLAlchemy URL:
   `postgresql+psycopg://postgres.<ref>:<password>@<host>:5432/postgres?sslmode=require`.
3. The API creates its tables on first start (Alembic migrations). It does not use
   Supabase Auth or storage; IDK Clips has its own accounts (Argon2id passwords).

## Step 2: API

Build and run the API image anywhere that runs containers (a VPS with Docker, or any
container platform with an always-on instance):

```bash
docker build -f docker/Dockerfile --build-arg WEB_BUILD=false -t openclip-api .
docker run -d --name openclip-api --restart unless-stopped \
  --env-file deploy/api.env -p 127.0.0.1:8000:8000 openclip-api
```

Start from `deploy/api.env.example`. It sets `OPENCLIP_MODE=hybrid`,
`OPENCLIP_ENVIRONMENT=production`, the database URL, CORS origin, public API URL and
`OPENCLIP_HOST=0.0.0.0` (inside the container). Keep `deploy/api.env` out of Git.

### TLS reverse proxy

Expose the API only through HTTPS. With Caddy (automatic certificates), see
`deploy/Caddyfile.example`:

```
api.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Behind a proxy, set `OPENCLIP_FORWARDED_ALLOW_IPS` to the proxy's address so rate limits
see real client addresses (the default trusts only `127.0.0.1`). When Caddy and the API run
in the same Compose network (`deploy/docker-compose.prod.yml`), the API is not published at
all and the setting is `*`. Never trust forwarded headers from every address on an API
that is reachable directly: clients could then fake their address and dodge rate limits.

## Step 3: web interface (Cloudflare Pages)

1. Create a Pages project connected to the repository (after it is published), or upload
   the build output directly with Wrangler.
2. Build settings: root directory `frontend`, build command `npm ci && npm run build`,
   output directory `out`, Node.js 22.
3. Environment variables: `NEXT_PUBLIC_API_URL=https://api.example.com` and, once the
   repository is public, `NEXT_PUBLIC_GITHUB_URL=https://github.com/<owner>/<repo>`.
4. The build writes `out/_headers` with a Content-Security-Policy that allows only the
   site, the API and the local worker bridge (`http://127.0.0.1:*`), plus HSTS and other
   security headers. Media files are never published.
5. Add the custom domain `app.example.com`.

## Step 4: check before going live

Run the pre-deployment check from the repository root:

```bash
backend/.venv/Scripts/python scripts/predeploy_check.py      # Linux: backend/.venv/bin/python
```

It runs the linters and test suites, builds the web interface, scans for secrets,
checks that no `.env` files, databases or media are part of the files to publish, and
audits dependencies. Then, manually:

- sign up with a new account, connect a worker, process a short video end to end;
- check with a second account that the first account's projects are not visible;
- confirm `https://api.example.com/api/docs` is hidden (production);
- confirm the response headers on `https://app.example.com` include the CSP.

## Scaling later

- **More API instances**: the in-memory rate limiter and login throttle are per process.
  Behind a load balancer, add sticky sessions or move rate limiting to the proxy.
- **Database**: move to a paid PostgreSQL plan; nothing in the code is provider specific.
- **Optional relay storage**: for users whose browser and worker are on different
  computers, an S3-compatible relay (for example R2 with short-lived signed URLs) can be
  added behind the existing storage interface. It is not implemented yet.
- **Community workers**: the job protocol could support volunteer processing in the
  future; it is deliberately disabled now.
