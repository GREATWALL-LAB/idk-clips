# Troubleshooting

Start with the requirements check: `scripts\windows\doctor.cmd` or
`bash scripts/linux/doctor.sh`. It explains most problems and how to fix them.

## Starting the app

**"IDK Clips is not set up yet."** Run `scripts\windows\setup.cmd`
(`bash scripts/linux/setup.sh`) once.

**"The web interface has not been built yet."** Run the setup again, or
`cd frontend && npm run build`.

**"Local mode has no accounts, so it only listens on this computer."** You set
`OPENCLIP_HOST` to a network address. Use `127.0.0.1`, or run server/hybrid mode with
accounts to share IDK Clips.

**Port 8000 is already in use.** Set `OPENCLIP_PORT=8010` in `.env`.

**The page says "IDK Clips is not reachable".** The API is not running, or (when you
built the web interface yourself) `NEXT_PUBLIC_API_URL` points to the wrong address.

**"This service only accepts requests from this computer."** Local mode was opened from
another device or through a name other than `localhost`/`127.0.0.1`. That is intended.

## Uploads

**"This file has no audio track"**: IDK Clips needs speech to work with.
**"The video is too short"**: the minimum is 10 seconds.
**"The file is larger than the … MB limit"**: raise `OPENCLIP_MAX_UPLOAD_MB` (local or
your own server).

## Transcription

**It is very slow.** Use a smaller speech model (`small` or `base`) on a CPU, or install
the GPU libraries ([installation](INSTALLATION.md#optional-gpu-transcription)).

**"GPU acceleration was not available … so the CPU was used"** in the transcript
warnings: the CUDA 12 libraries are missing or incompatible. Install
`backend/requirements-gpu.txt`, or ignore it (the CPU works, just slower).

**The first transcription waits a long time at 0%.** The speech model is being
downloaded (75 MB–3 GB). It is cached in `data/models/whisper` afterwards.

## AI clip suggestions

**"Ollama is not reachable."** Start the Ollama app or run `ollama serve`, then check
Settings → AI (or `OPENCLIP_OLLAMA_BASE_URL`).

**"No Ollama model is installed."** Run `ollama pull gemma3:4b` (or another model).

**"The local AI model took too long to answer."** Use a smaller model, or raise
`OPENCLIP_OLLAMA_TIMEOUT_SECONDS`.

**Fewer clips than requested.** The AI only returns moments that work as stand-alone
clips; nothing is invented to fill the number. Add clips by hand from the project page.

## Export

**"FFmpeg could not process this video."** The details are in the server or worker log.
Make sure your FFmpeg build includes `libx264` and `libass` (the builds from
`install-ffmpeg.cmd`, apt and Homebrew do).

**Captions look different in the preview.** The preview approximates the burned-in
captions with the same fonts and sizes; the exported MP4 is authoritative.

## Workers (online mode)

**"This pairing code is not valid."** Codes expire after 10 minutes and work once. Create
a new one in the dashboard.

**"Refusing to use an unencrypted http:// server address."** Use the `https://` address of
the server. Only for your own trusted network: `OPENCLIP_AGENT_ALLOW_HTTP=true`.

**"Your worker runs on another computer"** when uploading. Videos go straight from your
browser to the worker on the same computer. Open the website on the worker computer.

**The browser asks to "access other apps and services on this device".** This is how
browsers protect local services. Allow it for the IDK Clips website so it can reach your
worker on `127.0.0.1`.

**"Could not open the local bridge on 127.0.0.1:8787."** Another program uses the port.
Set `OPENCLIP_AGENT_BRIDGE_PORT` to a free port and restart the worker; the dashboard
learns the new port automatically.

**"This worker is no longer connected to an account."** It was disconnected in the
dashboard. Run `unpair`, then pair it again.

**A job says "Waiting for your worker".** Start the worker (`worker.cmd run`). Jobs wait
safely until it is online.

## Still stuck?

Open an issue with the output of the requirements check, the error message and the steps
to reproduce. Do not attach private videos or the `.env` and `credentials.json` files.
