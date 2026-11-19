# Installation

This guide installs IDK Clips on your own computer. The same installation is used to
[run locally](LOCAL_MODE.md) and to act as a [worker](WORKERS.md) for the website.

## Requirements

| Component | Needed for | Version |
|---|---|---|
| Python | The app and the worker | 3.11 or newer (3.13 tested) |
| Node.js | Building the web interface during setup | 20.9 or newer (LTS) |
| FFmpeg + FFprobe | Reading, cutting and exporting video | Any recent release (tested: 9.0) |
| Ollama + a model | AI clip suggestions | Optional but recommended |
| NVIDIA GPU + CUDA 12 libraries | Faster transcription | Optional; the CPU works too |

Disk space: about 2 GB for the software, plus speech models (75 MB–3 GB, downloaded on
first use), AI models (2–9 GB each) and your videos.

| Platform | Status |
|---|---|
| Windows 11 (x64) | Tested by the maintainers (with an NVIDIA RTX GPU) |
| Linux (x64) | Scripts provided, not yet verified by the maintainers |
| macOS (Apple silicon) | Scripts provided, not yet verified; transcription runs on the CPU |

## Windows

1. Install **Python** from [python.org](https://www.python.org/downloads/) and tick
   "Add python.exe to PATH".
2. Install **Node.js LTS** from [nodejs.org](https://nodejs.org/).
3. Get **FFmpeg**. The easiest way is the portable copy, which does not change your system:

   ```bat
   scripts\windows\install-ffmpeg.cmd
   ```

   It downloads the "release essentials" build linked from ffmpeg.org
   (gyan.dev), verifies its SHA-256 checksum and unpacks it into `tools\ffmpeg`.
   An FFmpeg already on your `PATH` works too.
4. Run the setup once. It creates `backend\.venv`, installs the Python and JavaScript
   packages into the project folder only, and builds the web interface:

   ```bat
   scripts\windows\setup.cmd
   ```

5. Optional, for AI suggestions: install [Ollama](https://ollama.com/download), start it,
   and download a model:

   ```bat
   ollama pull gemma3:4b
   ```

## Linux

```bash
sudo apt install python3 python3-venv ffmpeg     # Debian/Ubuntu; use your package manager
# Node.js 20+: https://nodejs.org/ or your distribution's nodejs package
bash scripts/linux/setup.sh
curl -fsSL https://ollama.com/install.sh | sh     # optional, see ollama.com for details
ollama pull gemma3:4b
```

## macOS

```bash
brew install python@3.13 node ffmpeg
bash scripts/linux/setup.sh
brew install ollama && ollama serve &             # or the Ollama app from ollama.com
ollama pull gemma3:4b
```

## Check the installation

The requirements checker only reads; it never installs or changes anything:

```bat
scripts\windows\doctor.cmd          :: Windows
bash scripts/linux/doctor.sh        # Linux / macOS
```

Example output:

```
IDK Clips (local mode): requirements check

  [ OK ]  Python                3.13.15
  [ OK ]  Data folder           writable, 136 GB free
  [ OK ]  FFmpeg                9.0.2-essentials_build-www.gyan.dev
  [ OK ]  FFprobe               9.0.2-essentials_build-www.gyan.dev
  [ OK ]  Speech transcription  NVIDIA GPU detected; the CPU is used if CUDA libraries are missing
  [ OK ]  Ollama (local AI)     0.40.16 1 model installed
  [WARN]  Speech model          'small' is not downloaded yet
                                -> It is downloaded automatically the first time you transcribe (about 484 MB).
```

## Optional: GPU transcription

faster-whisper uses CTranslate2. On Windows and Linux with an NVIDIA GPU, install the
CUDA 12 libraries into the virtual environment:

```bat
backend\.venv\Scripts\python -m pip install -r backend\requirements-gpu.txt
```

Without them, IDK Clips falls back to the CPU automatically and tells you in the
transcript warnings.

## Next steps

- [Run locally](LOCAL_MODE.md)
- [Connect this computer to the website as a worker](WORKERS.md)
- [Configuration](CONFIGURATION.md) and [troubleshooting](TROUBLESHOOTING.md)
