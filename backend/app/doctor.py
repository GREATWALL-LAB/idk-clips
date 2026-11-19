"""Requirements checker: ``python -m app doctor`` (also ``python -m app.agent doctor``).

Checks what IDK Clips needs on this computer and explains how to fix what is
missing. It only reads; nothing is installed or changed.
"""

from __future__ import annotations

import shutil
import sys
import uuid
from dataclasses import dataclass

from app.agent.capabilities import installed_models, system_components
from app.core.config import Settings
from openclip_processing.transcription import WHISPER_MODELS, WhisperTranscriber

MIN_PYTHON = (3, 11)
LOW_DISK_GB = 5


@dataclass
class Check:
    name: str
    state: str  # ok | warn | fail
    detail: str
    hint: str | None = None


def _python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= MIN_PYTHON:
        return Check("Python", "ok", version)
    return Check(
        "Python",
        "fail",
        version,
        f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer from python.org.",
    )


def _data_folder(settings: Settings) -> Check:
    probe = settings.data_dir / f".doctor-{uuid.uuid4().hex}"
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        return Check(
            "Data folder",
            "fail",
            f"not writable ({exc.__class__.__name__})",
            "Set OPENCLIP_DATA_DIR to a folder you can write to.",
        )
    free_gb = shutil.disk_usage(settings.data_dir).free / 1024**3
    if free_gb < LOW_DISK_GB:
        return Check(
            "Data folder",
            "warn",
            f"writable, only {free_gb:.1f} GB free",
            "Videos and clips need space. Free up disk space or move OPENCLIP_DATA_DIR.",
        )
    return Check("Data folder", "ok", f"writable, {free_gb:.0f} GB free")


def _speech_model(settings: Settings) -> Check:
    model = settings.whisper_default_model
    size = int(WHISPER_MODELS.get(model, {}).get("size_mb", 0))
    try:
        cached = WhisperTranscriber(settings.models_dir / "whisper").is_model_cached(model)
    except Exception:
        cached = False
    if cached:
        return Check("Speech model", "ok", f"'{model}' is downloaded")
    return Check(
        "Speech model",
        "warn",
        f"'{model}' is not downloaded yet",
        f"It is downloaded automatically the first time you transcribe (about {size} MB).",
    )


def _web_interface(settings: Settings) -> Check:
    if settings.web_dist is not None:
        return Check("Web interface", "ok", "built; served by this app")
    return Check(
        "Web interface",
        "warn",
        "no production build found",
        "Run 'npm run build' in the frontend folder (the setup script does this), "
        "or use 'npm run dev' while developing.",
    )


def collect(settings: Settings, *, worker: bool = False) -> list[Check]:
    checks = [_python(), _data_folder(settings)]
    for item in system_components(settings):
        required = bool(item.get("required"))
        status = item.get("status")
        state = "ok" if status == "ok" else ("fail" if required else "warn")
        detail = " ".join(str(part) for part in (item.get("version"), item.get("detail")) if part)
        checks.append(Check(str(item.get("name")), state, detail or str(status), item.get("hint")))
    models = installed_models(settings)
    if models:
        shown = ", ".join(models[:4]) + (" ..." if len(models) > 4 else "")
        checks.append(Check("AI models (Ollama)", "ok", shown))
    else:
        checks.append(
            Check(
                "AI models (Ollama)",
                "warn",
                "none found",
                "Clip suggestions need a local model. Install Ollama from https://ollama.com, "
                "then run for example: ollama pull gemma3:4b",
            )
        )
    checks.append(_speech_model(settings))
    if not worker:
        checks.append(_web_interface(settings))
    return checks


def run_doctor(settings: Settings, *, worker: bool = False) -> int:
    """Print the report. Returns 0 when everything required is present, otherwise 1."""
    checks = collect(settings, worker=worker)
    marks = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    title = "IDK Clips worker" if worker else f"IDK Clips ({settings.mode} mode)"
    print(f"\n{title}: requirements check\n")
    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"  {marks[check.state]}  {check.name.ljust(width)}  {check.detail}")
        if check.hint and check.state != "ok":
            print(f"          {' ' * width}  -> {check.hint}")
    failed = [check for check in checks if check.state == "fail"]
    warned = [check for check in checks if check.state == "warn"]
    print()
    if failed:
        print(
            f"  {len(failed)} required item(s) are missing. Fix them, then run this check again.\n"
        )
        return 1
    if warned:
        print(f"  Ready, with {len(warned)} note(s) above.\n")
    else:
        print("  Everything is ready.\n")
    return 0
