# Workers

A **worker** is IDK Clips running on your own computer, connected to your account on
an IDK Clips server in [hybrid mode](USING_ONLINE.md). It processes your videos:
transcription, AI moment detection, framing, captions and export.

## Connect a worker

1. Install IDK Clips on the computer ([installation](INSTALLATION.md)) and run the
   requirements check: `scripts\windows\worker.cmd doctor`.
2. On the website open **Workers → Connect a worker**. You get a one-time code such as
   `K7PD-3QXM` and the exact command.
3. On the computer, run that command:

   ```bat
   scripts\windows\worker.cmd pair --server https://api.example.com --code K7PD-3QXM
   ```

   ```bash
   bash scripts/linux/worker.sh pair --server https://api.example.com --code K7PD-3QXM
   ```

   Add `--name "Studio PC"` to choose the name shown in the dashboard.
4. Start it and leave the window open while you work:

   ```bat
   scripts\windows\worker.cmd run
   ```

## Commands

| Command | What it does |
|---|---|
| `pair --server URL --code CODE` | Connect this computer to your account |
| `run` | Wait for your jobs and process them |
| `status` | Show the pairing and whether the server accepts it |
| `doctor` | Check FFmpeg, the speech model and Ollama |
| `unpair` | Disconnect this computer and delete its saved credentials |
| `purge --yes` | Delete every video and clip this worker stores for your account |

## How it works

- The worker **only connects outwards** to the server over HTTPS and asks for work
  ("long polling", about every 20 seconds). You do not need to open ports or change your
  router.
- It reports progress, the transcript, clip suggestions and export results. Videos stay
  on the computer, in `data/storage/` of the installation.
- It runs a small **bridge** on `http://127.0.0.1:8787` so your browser on the same
  computer can hand it a video and play or download results. Change the port with
  `OPENCLIP_AGENT_BRIDGE_PORT`.
- AI suggestions use the worker's own Ollama (`OPENCLIP_OLLAMA_BASE_URL`, default
  `http://127.0.0.1:11434`). Pick the model per worker in the dashboard.
- One job runs at a time, because transcription and local AI share the GPU.

## Disconnections

The worker is built for laptops and flaky Wi-Fi. When the server is unreachable it keeps
retrying with increasing delays. A job that is already running continues; when the
connection is back, the worker reclaims its job and delivers the result. If a worker
stays silent for longer than its lease (90 seconds by default), the server returns the
job to the queue; after three attempts it is marked as failed with an explanation.

## Security

- **Pairing codes** work once, expire after 10 minutes, are stored only as hashes, and
  guessing is rate-limited.
- Each worker gets its **own credential** (a 256-bit token). The server stores only its
  hash; the worker stores it in `data/agent/credentials.json` (owner-only permissions on
  Linux and macOS; on Windows the file inherits the folder's access rules, so keep the
  installation inside your own user folder). Never share that file.
- **Disconnect** a worker in the dashboard (or run `unpair`) to revoke it immediately.
  Its waiting jobs are cancelled; files on the computer are not touched.
- A worker can only receive **jobs from its owner** and can only report results for the
  job it holds. The server validates every result.
- A worker understands a **fixed list of job types**. It cannot be told to run commands
  or to read files outside its own storage folder.
- The **bridge** listens on `127.0.0.1` only, refuses other `Host` names, accepts only the
  website's origins, and requires a short-lived transfer token that it checks with the
  server before reading or writing anything.
- Plain `http://` servers are refused, except a server on the same computer. For a server
  on your own trusted network set `OPENCLIP_AGENT_ALLOW_HTTP=true`.

## Running the worker in the background

The worker is a normal console program. To start it automatically, create a scheduled
task (Windows Task Scheduler, "At log on") or a `systemd --user` service (Linux) that runs
`worker.cmd run` / `worker.sh run`.

## Future: community workers

The protocol was designed so that volunteers could one day offer processing for others,
but this is **not enabled**: a worker only ever processes its own owner's jobs, and no
video is ever sent to someone else's computer.
