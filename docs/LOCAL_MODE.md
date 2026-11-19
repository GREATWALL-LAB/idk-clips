# Run locally

Local mode is the default. It is IDK Clips on your own computer with **no account,
no website and no uploads**: the video, transcript and clips never leave your machine
(unless you choose an external AI provider, see below).

## Start

```bat
scripts\windows\start.cmd           :: Windows
bash scripts/linux/start.sh         # Linux / macOS
```

Then open **http://localhost:8000**. One process serves both the web interface and the
API. Stop it with `Ctrl+C`.

## How local mode protects you

Because there is no sign-in, local mode only talks to this computer:

- it listens on `127.0.0.1` and refuses to start on a network address;
- it rejects requests from other machines and requests that do not use `localhost` or
  `127.0.0.1` as the address (this stops websites from reaching it through DNS tricks);
- websites cannot send commands to it: state-changing requests need a header that other
  sites can only send if the API allows their origin.

To share IDK Clips with other people, run it in **server** or **hybrid** mode with
accounts instead ([self-hosting](SELF_HOSTING.md)).

## Where your files are

Everything lives in the `data/` folder of the installation (change it with
`OPENCLIP_DATA_DIR`):

| Path | Contents |
|---|---|
| `data/openclip.db` | Projects, transcripts, clip settings (SQLite) |
| `data/storage/users/<id>/projects/<id>/` | The source video, thumbnail and exported clips |
| `data/models/whisper/` | Downloaded speech models |
| `data/tmp/` | Temporary files during processing (cleaned automatically) |

Deleting a project in the app removes its folder. **Settings → Your data** lets you delete
every project at once or remove source videos automatically after a number of days.

## Typical workflow

1. **New project** → choose a video file (MP4, MOV, MKV, WebM, AVI or M4V).
2. Choose the default **aspect ratio**, language, speech model and how many clips you want.
3. Processing starts: audio extraction, transcription, then AI clip detection. The
   progress shown is real progress reported by FFmpeg, faster-whisper and the AI model.
4. Open a clip to edit: timing, aspect ratio, framing, captions and text.
5. **Export MP4** and download it.

## AI providers

By default clip suggestions use **Ollama** on this computer. You can also
configure an OpenAI-compatible service (`OPENCLIP_EXTERNAL_AI_*`, see
[configuration](CONFIGURATION.md)). With an external provider, the **transcript text** is
sent to that service; the video never is.

Without any AI model you can still transcribe videos and create clips by hand.

## Development mode

`scripts\windows\start-dev.cmd` (or `bash scripts/linux/start-dev.sh`) runs the backend
with auto-reload and the Next.js dev server on http://localhost:3000.
