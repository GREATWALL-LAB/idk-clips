"""Local AI through Ollama's REST API (https://github.com/ollama/ollama/blob/main/docs/api.md)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from openclip_processing.errors import AIProviderError, JobCancelled
from openclip_processing.llm.base import extract_json
from openclip_processing.types import CancelCheck

UNREACHABLE = (
    "Ollama is not reachable. Start the Ollama app (or run 'ollama serve') and check the "
    "endpoint in Settings."
)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 600.0,
        num_ctx: int = 8192,
        keep_alive: str = "2m",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self._timeout = httpx.Timeout(connect=5.0, read=timeout, write=30.0, pool=5.0)
        self._transport = transport

    def _client(self, timeout: httpx.Timeout | None = None) -> httpx.Client:
        return httpx.Client(
            transport=self._transport, timeout=timeout or self._timeout, trust_env=False
        )

    # ---------------------------------------------------------------- info
    def version(self) -> str | None:
        with self._client(httpx.Timeout(5.0)) as client:
            response = client.get(f"{self.base_url}/api/version")
            response.raise_for_status()
            return response.json().get("version")

    def list_models(self) -> list[dict[str, Any]]:
        with self._client(httpx.Timeout(5.0)) as client:
            response = client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return list(response.json().get("models") or [])

    # ----------------------------------------------------------- generate
    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.2,
        should_cancel: CancelCheck | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": True,  # streamed so a cancelled job can stop mid-answer
            "think": False,
            "format": schema,  # structured output: the answer must match the JSON schema
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx, "seed": 42},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        parts: list[str] = []
        try:
            with (
                self._client() as client,
                client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response,
            ):
                if response.status_code == 404:
                    raise AIProviderError(
                        f"The Ollama model '{self.model}' is not installed. "
                        f"Install it with: ollama pull {self.model}"
                    )
                if response.status_code >= 400:
                    response.read()
                    raise AIProviderError(
                        f"Ollama returned an error (HTTP {response.status_code}).",
                        detail=response.text[:500],
                    )
                for line in response.iter_lines():
                    if should_cancel and should_cancel():
                        raise JobCancelled()
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise AIProviderError(
                            "Ollama reported an error.", detail=str(chunk["error"])[:500]
                        )
                    parts.append((chunk.get("message") or {}).get("content") or "")
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise AIProviderError(UNREACHABLE, detail=str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                "The local AI model took too long to answer. Try a smaller model.", detail=str(exc)
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("Could not talk to Ollama.", detail=str(exc)) from exc
        return extract_json("".join(parts))
