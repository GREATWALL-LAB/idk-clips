"""Local speech-to-text with faster-whisper.

Design rules:
- Always ``task="transcribe"``: the original spoken language is written down,
  never translated or "dubbed".
- If the user forces a language (English by default) but the audio sounds like a
  different language, the transcript carries a warning instead of silently
  producing a misleading result.
- ``device="auto"`` tries the NVIDIA GPU first and falls back to the CPU if the
  CUDA libraries are missing; the fallback is recorded as a warning.
"""

from __future__ import annotations

import gc
import logging
import os
import sysconfig
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openclip_processing.errors import JobCancelled, TranscriptionError
from openclip_processing.types import (
    CancelCheck,
    ProgressCallback,
    Segment,
    Transcript,
    Word,
    never_cancel,
    no_progress,
)

logger = logging.getLogger("openclip.transcription")

# Windows without Developer Mode cannot create symlinks; the Hugging Face cache still
# works (it copies files), so the noisy warning is silenced.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

#: Models offered in the UI. Sizes are approximate download sizes.
WHISPER_MODELS: dict[str, dict[str, Any]] = {
    "tiny": {
        "label": "Tiny",
        "size_mb": 75,
        "multilingual": True,
        "note": "Fastest, lowest accuracy",
    },
    "tiny.en": {
        "label": "Tiny (English)",
        "size_mb": 75,
        "multilingual": False,
        "note": "Fastest, English only",
    },
    "base": {"label": "Base", "size_mb": 145, "multilingual": True, "note": "Fast, basic accuracy"},
    "base.en": {
        "label": "Base (English)",
        "size_mb": 145,
        "multilingual": False,
        "note": "Fast, English only",
    },
    "small": {
        "label": "Small",
        "size_mb": 484,
        "multilingual": True,
        "note": "Good balance (recommended for CPU)",
    },
    "small.en": {
        "label": "Small (English)",
        "size_mb": 484,
        "multilingual": False,
        "note": "Good balance, English only",
    },
    "medium": {
        "label": "Medium",
        "size_mb": 1530,
        "multilingual": True,
        "note": "Accurate, slow on CPU",
    },
    "medium.en": {
        "label": "Medium (English)",
        "size_mb": 1530,
        "multilingual": False,
        "note": "Accurate, English only",
    },
    "large-v3-turbo": {
        "label": "Large v3 Turbo",
        "size_mb": 1620,
        "multilingual": True,
        "note": "Very accurate, best with a GPU",
    },
    "large-v3": {
        "label": "Large v3",
        "size_mb": 3100,
        "multilingual": True,
        "note": "Most accurate, needs a strong GPU",
    },
}

#: Languages offered in the UI (Whisper supports more; any ISO code it knows works).
LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "tr": "Turkish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "he": "Hebrew",
    "fa": "Persian",
    "hi": "Hindi",
    "bn": "Bengali",
    "ur": "Urdu",
    "ne": "Nepali",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "id": "Indonesian",
    "ms": "Malay",
    "vi": "Vietnamese",
    "th": "Thai",
    "tl": "Tagalog",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "sw": "Swahili",
}

GPU_FALLBACK_WARNING = (
    "GPU acceleration was not available (CUDA libraries missing or incompatible), "
    "so the CPU was used. See docs/INSTALLATION.md (Optional: GPU transcription) to enable the GPU."
)


def language_name(code: str | None) -> str:
    if not code:
        return "unknown"
    return LANGUAGES.get(code, code)


def is_english_only(model: str) -> bool:
    return model.endswith(".en")


def register_cuda_dll_directories() -> list[str]:
    """On Windows, make pip-installed NVIDIA cuBLAS/cuDNN DLLs loadable by CTranslate2."""
    if os.name != "nt":
        return []
    added: list[str] = []
    nvidia_root = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    if nvidia_root.is_dir():
        for bin_dir in sorted(nvidia_root.glob("*/bin")):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            added.append(str(bin_dir))
    return added


SAMPLE_RATE = 16_000


def read_wav(path: Path, seconds: float | None = None):  # -> numpy.ndarray
    """Read a 16 kHz, 16-bit mono WAV (as produced by FFmpegTools.extract_audio) as float32.

    The audio is decoded here instead of by faster-whisper's PyAV-based decoder,
    which is incompatible with recent PyAV releases (``metadata_errors`` was removed).
    """
    import numpy as np

    try:
        with wave.open(str(path), "rb") as wav:
            if (
                wav.getsampwidth() != 2
                or wav.getnchannels() != 1
                or wav.getframerate() != SAMPLE_RATE
            ):
                raise TranscriptionError("The extracted audio has an unexpected format.")
            count = (
                wav.getnframes()
                if seconds is None
                else int(min(wav.getnframes(), seconds * SAMPLE_RATE))
            )
            frames = wav.readframes(count)
    except (OSError, wave.Error) as exc:
        raise TranscriptionError("The extracted audio could not be read.", detail=str(exc)) from exc
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


@dataclass
class TranscriptionOptions:
    model: str = "small"
    language: str | None = "en"  # None or "auto" = detect automatically
    device: str = "auto"  # auto | cpu | cuda
    compute_type: str = "auto"
    beam_size: int = 5

    def validate(self) -> None:
        if self.model not in WHISPER_MODELS:
            raise TranscriptionError(f"Unknown speech model '{self.model}'.")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise TranscriptionError(f"Unknown device '{self.device}'.")
        language = self.normalized_language
        if is_english_only(self.model) and language not in (None, "en"):
            raise TranscriptionError(
                f"The '{self.model}' model only understands English. Choose a multilingual model."
            )

    @property
    def normalized_language(self) -> str | None:
        if self.language in (None, "", "auto"):
            return "en" if is_english_only(self.model) else None
        return self.language


class WhisperTranscriber:
    """Loads a Whisper model per job and unloads it afterwards to free (V)RAM."""

    def __init__(self, models_dir: Path, cpu_threads: int | None = None) -> None:
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cpu_threads = cpu_threads or max(1, (os.cpu_count() or 2) // 2)
        self._cuda_failed = False

    # ------------------------------------------------------------ helpers
    def is_model_cached(self, model: str) -> bool:
        from faster_whisper.utils import download_model

        try:
            download_model(model, local_files_only=True, cache_dir=str(self.models_dir))
        except Exception:
            return False
        return True

    def _device_plan(self, options: TranscriptionOptions) -> list[tuple[str, str]]:
        import ctranslate2

        def compute_for(device: str) -> str:
            if options.compute_type != "auto":
                return options.compute_type
            return "float16" if device == "cuda" else "int8"

        if options.device == "cpu":
            return [("cpu", compute_for("cpu"))]
        has_cuda = ctranslate2.get_cuda_device_count() > 0
        if options.device == "cuda":
            if not has_cuda:
                raise TranscriptionError("A CUDA GPU was requested, but none is available.")
            return [("cuda", compute_for("cuda"))]
        if has_cuda and not self._cuda_failed:
            return [("cuda", compute_for("cuda")), ("cpu", "int8")]
        return [("cpu", "int8")]

    # ----------------------------------------------------------------- run
    def transcribe(
        self,
        audio_path: Path,
        options: TranscriptionOptions,
        *,
        duration: float,
        progress: ProgressCallback = no_progress,
        should_cancel: CancelCheck = never_cancel,
    ) -> Transcript:
        options.validate()
        warnings: list[str] = []
        plan = self._device_plan(options)
        for index, (device, compute_type) in enumerate(plan):
            try:
                return self._run(
                    audio_path,
                    options,
                    device,
                    compute_type,
                    duration,
                    progress,
                    should_cancel,
                    warnings,
                )
            except (JobCancelled, TranscriptionError):
                raise
            except Exception as exc:
                is_last = index == len(plan) - 1
                if device == "cuda" and not is_last:
                    logger.warning("GPU transcription failed; falling back to CPU", exc_info=True)
                    self._cuda_failed = True
                    warnings.append(GPU_FALLBACK_WARNING)
                    continue
                raise TranscriptionError(
                    "Speech transcription failed. Check the server log for details.",
                    detail=f"{type(exc).__name__}: {exc}",
                ) from exc
        raise TranscriptionError("No transcription device is available.")  # pragma: no cover

    def _run(
        self,
        audio_path: Path,
        options: TranscriptionOptions,
        device: str,
        compute_type: str,
        duration: float,
        progress: ProgressCallback,
        should_cancel: CancelCheck,
        warnings: list[str],
    ) -> Transcript:
        from faster_whisper import WhisperModel

        if device == "cuda":
            register_cuda_dll_directories()
        cached = self.is_model_cached(options.model)
        size = WHISPER_MODELS[options.model]["size_mb"]
        progress(
            0.0,
            f"Loading speech model '{options.model}'"
            + ("" if cached else f" (first use: downloading about {size} MB)"),
        )
        model = WhisperModel(
            options.model,
            device=device,
            compute_type=compute_type,
            cpu_threads=self.cpu_threads,
            download_root=str(self.models_dir),
        )
        try:
            audio = read_wav(audio_path)
            language = options.normalized_language
            if language and not is_english_only(options.model) and audio.size > SAMPLE_RATE:
                detected, probability, _ = model.detect_language(audio=audio[: 30 * SAMPLE_RATE])
                if detected != language and probability >= 0.75:
                    warnings.append(
                        f"The audio sounds like {language_name(detected)} "
                        f"({probability:.0%} confidence), but {language_name(language)} was "
                        "selected. The transcript may be inaccurate; try Auto-detect."
                    )

            segments_iter, info = model.transcribe(
                audio,
                language=language,
                task="transcribe",
                beam_size=options.beam_size,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                word_timestamps=True,
                condition_on_previous_text=False,
                hallucination_silence_threshold=2.0,
            )
            total = duration or float(info.duration or 0)
            segments: list[Segment] = []
            progress(0.0, "Transcribing speech")
            for raw in segments_iter:
                if should_cancel():
                    raise JobCancelled()
                text = raw.text.strip()
                if not text:
                    continue
                words = [
                    Word(
                        start=round(float(w.start), 3),
                        end=round(float(w.end), 3),
                        text=w.word.strip(),
                        probability=round(float(w.probability), 3),
                    )
                    for w in (raw.words or [])
                    if w.word.strip()
                ]
                segments.append(
                    Segment(
                        id=len(segments),
                        start=round(float(raw.start), 3),
                        end=round(float(raw.end), 3),
                        text=text,
                        words=words,
                    )
                )
                if total > 0:
                    progress(min(float(raw.end) / total, 0.999), "Transcribing speech")
            progress(1.0, "Transcribing speech")
            if not segments:
                warnings.append("No speech was detected in this video.")
            return Transcript(
                language=str(info.language),
                language_probability=round(float(info.language_probability), 3)
                if info.language_probability is not None
                else None,
                duration=round(float(info.duration or total), 3),
                model=options.model,
                device=device,
                segments=segments,
                warnings=warnings,
            )
        finally:
            del model
            gc.collect()
