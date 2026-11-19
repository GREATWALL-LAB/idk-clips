"""Provider interface and JSON helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from openclip_processing.errors import AIProviderError
from openclip_processing.types import CancelCheck

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.2,
        should_cancel: CancelCheck | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object (dict) that should follow ``schema``."""
        ...


def extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object in ``text`` (tolerates code fences and chatter)."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start < 0:
            raise AIProviderError(
                "The AI model did not return valid JSON.", detail=text[:500]
            ) from None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start : index + 1])
                    except json.JSONDecodeError as exc:
                        raise AIProviderError(
                            "The AI model returned malformed JSON.", detail=text[:500]
                        ) from exc
                    break
        else:
            raise AIProviderError("The AI model returned incomplete JSON.", detail=text[:500])
    if not isinstance(value, dict):
        raise AIProviderError("The AI model returned an unexpected format.", detail=text[:500])
    return value
