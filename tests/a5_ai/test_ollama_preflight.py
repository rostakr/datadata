from __future__ import annotations

import io
import json
import socket
import urllib.error

import pytest

from analyzazprav.a5_ai.providers import (
    OllamaProvider,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
)


class FakeResponse:
    def __init__(self, payload):
        if isinstance(payload, bytes):
            self._payload = payload
        else:
            self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._payload


def test_preflight_accepts_exact_requested_model_without_sending_prompt(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data, timeout))
        return FakeResponse({"models": [{"name": "qwen3:8b"}, {"model": "llama3.2:latest"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaProvider("qwen3:8b", preflight_timeout_seconds=1.25)

    result = provider.preflight()

    assert result.ready is True
    assert result.requested_model == "qwen3:8b"
    assert result.available_models == ("llama3.2:latest", "qwen3:8b")
    assert calls == [("http://localhost:11434/api/tags", "GET", None, 1.25)]


def test_preflight_rejects_missing_model(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse({"models": [{"name": "llama3.2:latest"}]}),
    )

    with pytest.raises(ProviderUnavailable, match="not installed"):
        OllamaProvider("qwen3:8b").preflight()


def test_preflight_distinguishes_timeout(monkeypatch):
    def fake_urlopen(request, timeout):
        raise socket.timeout("slow local daemon")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderTimeout, match="timed out"):
        OllamaProvider("qwen3:8b").preflight()


def test_preflight_distinguishes_unavailable_server(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderUnavailable, match="unavailable"):
        OllamaProvider("qwen3:8b").preflight()


def test_preflight_rejects_malformed_json(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse(b"not-json"),
    )

    with pytest.raises(ProviderError, match="invalid JSON"):
        OllamaProvider("qwen3:8b").preflight()


def test_preflight_rejects_missing_models_array(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse({"version": "test"}),
    )

    with pytest.raises(ProviderError, match="models array"):
        OllamaProvider("qwen3:8b").preflight()
