from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping

from .base import ProviderError, ProviderTimeout, ProviderUnavailable


@dataclass(frozen=True)
class OllamaPreflight:
    base_url: str
    requested_model: str
    available_models: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.requested_model in self.available_models

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "base_url": self.base_url,
            "requested_model": self.requested_model,
            "available_models": list(self.available_models),
            "ready": self.ready,
        }


class OllamaProvider:
    def __init__(
        self,
        model_name: str,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 120.0,
        preflight_timeout_seconds: float = 5.0,
        response_format: str | Mapping[str, Any] = "json",
        think: bool | str | None = None,
        temperature: float | None = None,
        num_predict: int | None = None,
    ) -> None:
        self._model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.preflight_timeout_seconds = preflight_timeout_seconds
        self.response_format = response_format
        self.think = think
        self.temperature = temperature
        self.num_predict = num_predict

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _read_json(self, request: urllib.request.Request, *, timeout_seconds: float) -> Mapping[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeout(f"Ollama request timed out: {reason}") from exc
            raise ProviderUnavailable(f"Ollama is unavailable at {self.base_url}: {reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeout(f"Ollama request timed out: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama returned invalid JSON envelope") from exc
        if not isinstance(body, Mapping):
            raise ProviderError("Ollama returned a non-object JSON envelope")
        return body

    def preflight(self) -> OllamaPreflight:
        """Verify the local server and exact requested model without sending evidence."""

        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        body = self._read_json(request, timeout_seconds=self.preflight_timeout_seconds)
        raw_models = body.get("models")
        if not isinstance(raw_models, list):
            raise ProviderError("Ollama /api/tags response did not contain a models array")

        names: set[str] = set()
        for item in raw_models:
            if not isinstance(item, Mapping):
                raise ProviderError("Ollama /api/tags models array contains a non-object entry")
            for key in ("name", "model"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())

        result = OllamaPreflight(
            base_url=self.base_url,
            requested_model=self.model_name,
            available_models=tuple(sorted(names)),
        )
        if not result.ready:
            available = ", ".join(result.available_models) if result.available_models else "none"
            raise ProviderUnavailable(
                f"Ollama model {self.model_name!r} is not installed; available models: {available}"
            )
        return result

    def analyze(self, *, system_prompt: str, user_prompt: str) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": self.response_format,
            "stream": False,
        }
        if self.think is not None:
            payload["think"] = self.think
        options: dict[str, Any] = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.num_predict is not None:
            options["num_predict"] = self.num_predict
        if options:
            payload["options"] = options

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        body = self._read_json(request, timeout_seconds=self.timeout_seconds)
        try:
            content = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError("Ollama response did not contain message.content") from exc
        if isinstance(content, Mapping):
            return content
        if not isinstance(content, str):
            raise ProviderError("Ollama message.content was not a string or object")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama model output was not valid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise ProviderError("Ollama model output must be a JSON object")
        return parsed
