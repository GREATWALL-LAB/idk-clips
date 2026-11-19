# Use online

The website version of IDK Clips runs in **hybrid mode**: you sign in on the website,
and your own computer does the video work. This keeps the service free to run, because
nobody has to rent GPU servers, and it keeps your videos on your own machine.

## What runs where

| The website (server) | Your computer (worker) |
|---|---|
| Your account and sign-in | Receiving the video from your browser |
| Projects, titles and settings | Reading and checking the video (FFprobe) |
| Transcripts and clip timings (text) | Transcription (faster-whisper) |
| The job queue and progress | Finding moments (your local Ollama) |
| Which worker holds which project | Cropping, captions and MP4 export (FFmpeg) |
| | Storing the source video and exported clips |

The server never stores your videos in hybrid mode.

## Getting started

1. **Create a free account** on the website. There are no plans or limits to choose.
2. **Install IDK Clips** on the computer that should process your videos
   ([installation](INSTALLATION.md)).
3. **Connect it as a worker**: in the dashboard open **Workers → Connect a worker**. Copy
   the command it shows and run it on that computer, then start the worker
   ([details](WORKERS.md)):

   ```bat
   scripts\windows\worker.cmd pair --server https://api.example.com --code ABCD-EFGH
   scripts\windows\worker.cmd run
   ```

4. **Create a project** in the browser **on that same computer**. The file goes straight
   from your browser to the worker on `127.0.0.1`; it is not uploaded to the website.
5. Processing, editing and export work as in local mode. Previews and downloads also
   come straight from your worker.

## Good to know

- **Use the browser on the worker computer** for uploading, previewing and downloading.
  From other devices you can still see projects, transcripts and clip lists, and you can
  edit timings and captions, but video files are only reachable on the worker computer.
- **The worker must be running** to process. Jobs wait in the queue while it is offline
  and start when it reconnects. If a worker disappears in the middle of a job, the job is
  offered to it again a few times and then marked as failed with an explanation.
- Some browsers ask for permission before a website may talk to apps on your computer
  ("access other apps and services on this device"). Allow it for the IDK Clips website.
- **Deleting** a project deletes its text on the server immediately and tells your worker
  to delete the files the next time it is online.
- **Retention**: in Settings → Your data you can have source videos deleted automatically
  after 1, 7, 30 or 90 days.

## Supported browsers

The direct browser-to-worker transfer relies on browsers treating `127.0.0.1` as a secure
local address. It was verified in a Chromium-based browser. Firefox is expected to work;
Safari has historically restricted these requests and is not verified.

## Running your own website

See [self-hosting](SELF_HOSTING.md) and [deployment](DEPLOYMENT.md).
