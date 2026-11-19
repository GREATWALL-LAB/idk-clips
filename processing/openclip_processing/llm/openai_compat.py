"""Optional external AI through any OpenAI-compatible Chat Completions API.

Works with services that implement ``POST {base_url}/chat/completions`` (for example
OpenAI, Groq, OpenRouter, Together, Mistral, LM Studio, vLLM, or Ollama's own /v1
endpoint). The API key is read by the backend from an environment variable and is
only ever sent to the configured base URL; it never reaches the browser.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from openclip_processing.errors import AIProviderError, JobCancelled
from openclip_processing.llm.base import extract_json
from openclip_processing.types import CancelCheck


class OpenAICompatibleProvider:
    name = "external"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._timeout = httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=10.0)
        self._transport = transport

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.2,
        should_cancel: CancelCheck | None = None,
    ) -> dict[str, Any]:
        if should_cancel and should_cancel():
            raise JobCancelled()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": f"{system}\n\nReply with one JSON object that follows this JSON schema:\n"
                    f"{json.dumps(schema)}",
                },
                {"role": "user", "content": user},
            ],
        }
        try:
            with httpx.Client(
                transport=self._transport, timeout=self._timeout, trust_env=False
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError("The external AI provider did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                "Could not reach the external AI provider.", detail=str(exc)
            ) from exc
        if response.status_code in (401, 403):
            raise AIProviderError("The external AI provider rejected the API key.")
        if response.status_code == 429:
            raise AIProviderError(
                "The external AI provider is rate limiting requests. Try again later."
            )
        if response.status_code >= 400:
            # The body may echo request details, so only a short excerpt goes to the log.
            raise AIProviderError(
                f"The external AI provider returned HTTP {response.status_code}.",
                detail=response.text[:300],
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "The external AI provider returned an unexpected response."
            ) from exc
        return extract_json(content or "")
