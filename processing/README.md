# openclip-processing

The media-processing library behind IDK Clips. It has no web-framework or
database dependencies, so it can be tested and reused on its own.

| Module | Purpose |
|---|---|
| `binaries.py` | Locate FFmpeg/FFprobe (configured path, `tools/ffmpeg/bin`, or `PATH`) |

More modules are added as the processing phases land; see the main
[README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

Install (from the project root, inside the backend virtual environment):

```bash
python -m pip install -e processing
```
