# IDK Clips — implementation record

Working record of the build. Status values: `DONE` (verified with the evidence named),
`PARTIAL`, `NOT RUN`. Nothing is marked DONE without a real run. Last updated 2026-11-17.

## 1. Starting point (inspected 2026-11-13)

| Area | State before this work |
|---|---|
| `backend/` FastAPI app | Working: Argon2id accounts, session cookies, CSRF, rate limits, owner-scoped data, Alembic 0001–0002, in-process job thread or Celery. |
| `processing/` library | Working: FFmpeg, faster-whisper, Ollama / OpenAI-compatible detection, ASS captions, 4 ratios, subject framing. |
| `frontend/` Next.js 16 | Working dark UI, no tests. Editor offered only 9:16 crop/fit/original. |
| Tests | Backend 109/110 (one stale test), processing 28/28. |
| Missing | Hybrid workers, account-free local mode, YouTube flow, README/docs, Docker, deployment config, frontend tests, brand identity, storytelling homepage. |

## 2. Architecture decisions

See `docs/ARCHITECTURE.md` ("Decisions"). In short: three run modes (`local`, `server`,
`hybrid`); one job pipeline split into spec / compute / events; user-owned workers with
pairing codes, hashed tokens, leases and a loopback bridge; static-export frontend; YouTube
as reference-and-attach only; static host + small API container + managed PostgreSQL.

## 3. Work done

| # | Step | Status | Evidence |
|---|---|---|---|
| 1 | Inspect project, baseline tests | DONE | pytest backend 109/110, processing 28/28 |
| 2 | Run modes, account-free local user, loopback guard | DONE | `tests/test_local_mode.py` (10 tests) |
| 3 | Job pipeline split (spec / compute / events) | DONE | Existing pipeline tests still pass through the new path |
| 4 | Workers: model, migration 0003, pairing, agent API, leases | DONE | `tests/test_workers.py` (23 tests) |
| 5 | Worker agent: client, runner, bridge, CLI, doctor | DONE | `tests/test_agent.py` (30 tests, real FFmpeg); `python -m app doctor` run |
| 6 | YouTube reference, per-clip ratio, retention, account deletion | DONE | `tests/test_youtube.py`, `tests/test_account.py` |
| 7 | Frontend: brand system, static export, query routes | DONE | `npm run build`: 205 files, 4.1 MB |
| 8 | Frontend: mode-aware auth, workers page, bridge transfers, ratio editor | DONE | Browser end-to-end runs below |
| 9 | Homepage scroll storytelling, docs, privacy, terms | DONE | Browser check desktop + 375 px; 18 doc pages, 0 broken links |
| 10 | Frontend tests | DONE | Vitest 35/35 |
| 11 | README, docs, open-source files | DONE | `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `docs/*` |
| 12 | Docker, deployment config, Linux scripts | PARTIAL | Files written; Docker **NOT RUN** (Docker not installed); Linux scripts syntax-checked only (`bash -n`), **not run on Linux/macOS** |
| 13 | End-to-end verification, security scan, production build | DONE | `scripts/predeploy_check.py`: 13 passed, 0 failed, 1 warning |

## 4. End-to-end verification (2026-11-17, Windows 11, RTX 5060, built-in Chromium browser)

Isolated data folders were used; the existing `data/openclip.db` was not touched.

**Local mode** (no account): upload through the real form (4-min TTS sample) → tiny.en
transcription → `gemma4:12b` via Ollama suggested 7 clips (8 requested) → clip switched to
9:16 in the editor → export → file probed: 1080×1920, H.264 + AAC, SAR 1:1, 27.2 s.

**Hybrid mode**: registration → pairing code in the UI → `worker pair` → `worker run` →
upload from the browser straight to the worker bridge (server stored 0 video files) →
processing on the worker (7 clips) → export in 16:9 on the worker → 1920×1080 file →
preview and download served by the bridge → project deleted in the UI → worker purge job
removed all files; server rows removed.

**Responsive**: homepage, dashboard, projects, project, editor, workers, settings, new
project and docs pages have no horizontal overflow at 375 px (two overflow bugs found and
fixed during this check).

## 4b. Rebrand, sign-in buttons, administrator lockdown, 16:9 layout (2026-11-18)

- **Name**: every user-facing text now says IDK Clips (pages, titles, metadata, logo, docs,
  scripts, CLI output, API title). Internal identifiers keep the old prefix on purpose so
  existing installations, data and clients keep working: `OPENCLIP_*` settings, the
  `openclip_processing` package, the session cookie, the CSRF header value, `openclip.db`,
  Docker service and volume names. New: Open Graph/Twitter metadata, a web app manifest,
  SVG and Apple icons, a social card (linked only when `NEXT_PUBLIC_SITE_URL` is set).
- **Header**: "Log in" and "Create account" on the public site header (desktop bar and
  phone menu), "Dashboard" when signed in, "Open app" in local mode; "Create account" is
  hidden when sign-ups are closed.
- **Administrators** (security fix): public sign-up used to make the first account the
  administrator; that was closed. (Superseded on 2026-11-18 by removing the administrator
  system entirely, see 4c.)
- **16:9 layout bug**: in the clip editor at 1024–1279 px, a 16:9 (or 1:1) preview took the
  whole row and squeezed the controls to 134 px, so "Download MP4" overflowed its card by
  48 px and the page scrolled sideways. Square and landscape previews now sit above the
  controls until 1280 px, the controls column has a 340–360 px minimum, and the export card
  sizes itself with a container query. The preview dialog uses the wide layout for 1:1
  and 16:9 and offers the download.
- **Verified**: all four ratios at 1440, 1280, 1024, 768 and 375 px (no horizontal scroll,
  download inside its card, exact preview ratios); exported files probed at 1080×1920,
  1080×1350, 1080×1080 and 1920×1080 (H.264 + AAC, square pixels); sign-up, log-in,
  and every refusal tested in the browser against a local hybrid server.

## 4c. No admin system, security, limits, caching, SEO, CI, live deployment (2026-11-18)

- **No administrator system**: roles, admin API, admin command and admin screens removed;
  migration 0004 drops the role column (accounts kept). AI settings are per user online;
  the Ollama endpoint is fixed by the server (closes an SSRF path). Tests prove there are
  no admin routes and that every ID-taking route refuses other users' data.
- **Security**: HSTS, Permissions-Policy, COOP/CORP on API responses; safe link schemes in
  rendered docs; request-size limits; failed-request throttling; per-user job cap and
  optional daily quota; trusted client-IP header for proxies.
- **Caching/performance**: composite indexes (migration 0005), cacheable `/meta`,
  immutable hashed assets, no-store for private data, Range requests for video.
- **SEO/GEO**: per-page titles, descriptions and canonicals; sitemap.xml, robots.txt,
  llms.txt; SoftwareApplication, WebSite, FAQPage and TechArticle JSON-LD; FAQ section;
  app pages noindex; `npm run check:site` fails the build on SEO or link problems.
- **Open source/CI**: issue and PR templates, CI (lint, tests, build, site check, secret
  scan, audits), CodeQL, Dependabot, daily security audit, Vercel deploy and uptime
  workflows, license check (`scripts/check_licenses.py`: no incompatible licenses).
- **Live**: https://idk-clips.vercel.app (Vercel Hobby, free) with the API as a serverless
  function on a free Neon database.

## 4d. 18+ confirmation and email OTP verification (2026-11-18, priority task)

- Sign-up asks "Are you 18 years of age or older?" with Yes and No. No blocks sign-up
  (for the browser session) and the server refuses any sign-up without an explicit Yes;
  the answer's time is stored (`age_confirmed_at`, migration 0006).
- After sign-up, Supabase Auth emails a one-time code; no session exists until the code
  is verified (`/auth/verify-email`). Codes expire (10 min), can be resent once a minute
  (`/auth/resend-code`), and five wrong codes require a new code. Login refuses accounts
  that are not 18+ confirmed or not verified; older accounts answer the age question and
  verify at their next login. Every protected endpoint and every worker request re-checks.
- Tested: 28 backend tests (rules, limits, expiry, cooldown, re-checks, workers, the
  Supabase request format), 9 web tests, and the full flow in a browser against a local
  stand-in for Supabase Auth (age No/Yes, wrong and right code, resend cooldown, login,
  an older account upgraded by migration 0006). **Not yet tested: real email delivery**,
  which needs a Supabase project and an SMTP provider (see Deployment > Email verification).
- Live site: verification build deployed; sign-ups stay closed with an explicit message
  until Supabase is configured. One account was created on the live site before sign-ups
  were closed; it must confirm its age and verify its email before it can be used.

## 4e. Email delivery setup and password reset (2026-11-18)

- **Security fix**: `/auth/verify-email` returned early for already verified accounts and
  then created a session, so any verified account could be entered with its address and
  any code. Fixed (an already verified account is always refused there), regression test
  added, deployed. Not exploitable on the live site before the fix: it had no verified
  accounts (sign-ups closed, no email delivery).
- **Password reset**: "Forgot password?" on the log-in page; a code from Supabase's
  "Reset Password" email (`/auth/v1/recover`, verified as type `recovery`) sets a new
  password and ends every session. Same expiry, 60 s cooldown and attempt limits; no
  answer reveals whether an address has an account. Tested in 6 backend tests, a web
  test and in the browser against the local Supabase stand-in.
- **Bug fix**: the web client dropped the body of 202 answers, so "Send a new code" and
  the reset request failed in the browser. Fixed, with a regression test.
- **Supabase** (in the Founder's account, Free plan): organization "IDK Clips", project
  `idk-clips` (ref `nsdaptagdrccapvdtivh`, Americas), Email OTP 6 digits / 600 s, Site
  URL `https://idk-clips.vercel.app`, automatic RLS on new tables. Rate limits left at
  Supabase defaults (30 code requests and 30 verifications per 5 min, 60 s between emails
  to one user).
- **Blocked**: Supabase only allows editing email templates after custom SMTP is set up,
  and its default templates send a sign-in **link**, not the code IDK Clips asks for. The
  built-in sender also reaches only organization members, 2 emails per hour. Opening
  resend.com and brevo.com was refused in the browser, and no domain with DNS access
  exists (SPF/DKIM/DMARC cannot be set on `*.vercel.app`). The branded templates are
  ready in `deploy/supabase/templates/`. The live site keeps sign-ups closed until SMTP
  and templates are in place; the Supabase URL and key are not yet set in Vercel on
  purpose, so no code-less emails go out.

## 4f. Production email delivery (2026-11-18)

- **Provider**: Brevo free plan (300 emails/day), chosen by the Founder; no domain, so the
  sender is the Founder's verified Gmail address (approved) with the name "IDK Clips".
  Brevo flags freemail senders as not compliant with Gmail/Yahoo/Microsoft DMARC rules:
  some codes may land in spam until a domain with SPF/DKIM/DMARC is used.
- **Supabase**: custom SMTP `smtp-relay.brevo.com:587`, login `c40808001@smtp-brevo.com`,
  SMTP key entered by the Founder (never seen or stored here). Branded templates applied
  to "Magic link or OTP", "Confirm sign up" and "Reset password". Supabase limits: 30
  emails per hour, at least 60 s between emails to one address.
- **IDK Clips**: `OPENCLIP_SUPABASE_URL` and the publishable key set in Vercel; publishable
  keys are now sent only as `apikey` (not as a Bearer token). Sign-ups reopened.
- **First attempt failed** with `535 5.7.8 Authentication failed` from Brevo (the saved
  key was not a valid SMTP key); the Founder replaced it.
- **Verified in production**: a real code email reached the Founder's Gmail and verified
  the account on https://idk-clips.vercel.app (`email_verified` and `age_confirmed` true,
  protected API 200).
- Still to test in production: password reset email, resend after 60 s, a wrong code, and
  an expired code (10 minutes).

## Pending work (in the original order)

1. Supabase project + SMTP provider for email codes (needs the Founder), then a real
   delivery test and re-opening sign-ups.
2. DONE 2026-11-18 (all 13 footer links return 200 on the live site; privacy, terms and security rewritten to match the implementation; sitemap, canonicals and phone layout checked). Footer and public pages (Founder's spec of 2026-11-18): footer groups Product
   (Features `/#features`, How it works `/#how-it-works`, Open the app `/dashboard/`),
   Documentation (`/docs/installation/`, `/docs/workers/`, `/docs/self-hosting/`,
   `/docs/troubleshooting/`), Project (`/docs/contributing/`, `/docs/security/`,
   `/docs/license/`) and Legal (`/privacy/`, `/terms/`, `/docs/code-of-conduct/`). Every
   page complete and accurate (privacy, terms, security and license must match the real
   implementation, including age confirmation, Supabase email codes and no admin
   system); no `localhost:8200` or other development addresses; responsive; titles,
   descriptions, canonicals and indexing settings; sitemap entries; every footer link
   checked on the deployed site. Then the final documentation pass (README: live URL,
   stack, automation).
3. DONE 2026-11-18: real-app run on https://idk-clips.vercel.app with a worker paired to
   the Founder's account: pairing code, worker online, 3.8-minute talk sent to the worker
   (nothing uploaded to the server), transcription (faster-whisper "small"), 7 clips from
   gemma4:12b, a 16:9 export (1920x1080 H.264 + AAC, 28.4 s), download from the worker
   with a short-lived token (a wrong token is refused), project deleted on the site and
   its files deleted on the worker, test worker removed. The built-in browser pane blocks
   public sites from reaching 127.0.0.1, so the one browser-to-worker upload request was
   sent from this computer with the same token and headers the web page uses.
4. Git repository: initial commit, secret scan of the history.
5. GitHub: create the public repository (needs the Founder: `gh` is not installed and no
   repository exists), push, set `NEXT_PUBLIC_GITHUB_URL`, add the Vercel secrets for the
   deploy workflow.
6. Search Console / Bing verification (needs the Founder's accounts).
7. Final report.

## 5. Open items for the Founder

| Item | Why it needs you |
|---|---|
| Push to GitHub, publish, deploy | Explicitly reserved for your approval. Nothing was pushed, published or deployed. |
| `frontend/public/_test-sample.mp4` (20 MB, from an earlier session) | Not deleted. Ignored by Git and excluded from builds; remove it before sharing the folder. |
| `data/browser-test/` (contains a `TEST-ACCOUNT.txt` from an earlier session) | Not read and not changed. It is ignored by Git; delete it if no longer needed. |
| Hosting accounts (Cloudflare, Supabase, API host) | Creating accounts and any spending need your approval. |
| `NEXT_PUBLIC_GITHUB_URL` | Set once the repository exists; GitHub links stay hidden until then. |
| Linux/macOS verification, Docker build | Not available in this environment. |
| `NEXT_PUBLIC_SITE_URL` | Set it for the hosted site so social previews use the right address. |
