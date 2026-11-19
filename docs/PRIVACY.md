# Privacy

IDK Clips is built to need as little of your data as possible. This notice explains what
is stored, where, and why, for each way of using it. It describes the software as it is
and the public website at https://idk-clips.vercel.app. If you use a copy run by someone
else, that operator is responsible for it and may add their own details.

## Running locally

Nothing is sent to the IDK Clips project or to any website. Your videos, transcripts,
clips and settings stay in the `data/` folder of your installation. There is no account,
no analytics and no telemetry.

Outgoing connections happen only when you use these features:

- downloading a speech model the first time (from Hugging Face);
- an external AI provider, if one is configured and chosen (the **transcript text** is
  sent to it, never the video);
- a YouTube link (the video ID is sent to YouTube's oEmbed service to show the title);
- importing from a direct link (the file is downloaded from that address).

## Using the website (https://idk-clips.vercel.app)

The website runs in hybrid mode: it keeps your account and project details, and your own
computer (your paired worker) stores and processes the videos.

### What the website stores

| Data | Where | Why |
|---|---|---|
| Email address, display name | The website's database | Your account |
| Password | The website's database, as an Argon2id hash only | Logging in |
| Your answer to "Are you 18 years of age or older?" (Yes) and when you gave it | The website's database | Accounts are for adults only |
| When your email address was verified; when the latest code was sent and how many wrong codes were entered | The website's database | Email verification, password reset, abuse limits |
| Account creation and last login times; preferences (source-video retention, your AI model choice) | The website's database | Running your account |
| Session tokens | A cookie in your browser (14 days); only a hash on the server | Keeping you logged in |
| Project names, settings, transcripts, clip titles, timings and captions | The website's database | Showing and editing your projects |
| YouTube link and its public title, channel and thumbnail address | The website's database | Reference for the project |
| Worker name, platform, app version, installed AI models, last seen time | The website's database | Showing and managing your workers |
| **Videos and exported clips** | **Only on your own worker computer** | Processing |

The website never receives your videos: your browser sends them directly to your worker
on the same computer and plays or downloads results from there. No identity documents are
ever requested; the age question is a simple Yes or No.

### Services that handle your data for the website

| Service | What it receives | Why |
|---|---|---|
| **Vercel** (hosting) | Every request to the website, including your IP address and browser details, in its request logs | Serving the website and its API |
| **Neon** (PostgreSQL, through the Vercel Marketplace) | The website's database described above | Storage |
| **Supabase Auth** | Your email address; it keeps a user record and its own logs of code requests | Creating, emailing and checking one-time codes for email verification and password reset |
| **Brevo** (email delivery) | Your email address and the content of the code email | Delivering the code emails sent by Supabase |

Supabase is used only for these codes: your password and projects are never sent to it.
The code emails are sent with the sender name "IDK Clips" from the website operator's
email address.

The website does not use advertising, tracking cookies or third-party analytics. Its own
logs record technical details of requests (time, path, status, duration and a request
ID) for security and debugging, never passwords, codes, tokens or video content. Your IP
address is used, in memory only, to limit repeated requests and failed attempts.

## Running on a self-hosted server (server mode)

In server mode the operator's server also stores and processes the videos. Ask the
operator how long they keep them.

## Deleting your data

- **Delete a project**: removes it with its transcript and clips. On the website, your
  worker deletes the files the next time it is online.
- **Settings → Your data → Delete all projects**.
- **Automatic deletion**: have source videos removed 1, 7, 30 or 90 days after upload.
- **Delete my account** (asks for your password): removes your account, projects, clips
  and sessions from the website's database and disconnects your workers.
- **On a worker**: `worker purge --yes` deletes all files it stored for your account;
  `worker unpair` removes its credentials.

Not removed automatically: the email address in Supabase Auth's user record (the website
cannot delete it without a secret key it deliberately does not hold), and entries already
written to the request logs of Vercel, Supabase and Brevo, which those services keep for
their own retention periods. To have the Supabase record removed, contact the operator.

## Contact

Questions about the public website or the software go to the project maintainers through
the repository's issue tracker. Report security problems privately as described in the
[security policy](../SECURITY.md).
