from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


class RuntimeUnavailable(RuntimeError):
    pass


# Compatibility name for historical callers/tests.
A5Unavailable = RuntimeUnavailable


def a5_available() -> bool:
    return runtime_available()


def runtime_available() -> bool:
    try:
        import analyzazprav.runtime  # noqa: F401
    except ImportError:
        return False
    return True


def check_local_a5_provider(
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Compatibility wrapper for ``check_local_runtime_provider``."""

    return check_local_runtime_provider(
        model_name=model_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def check_local_runtime_provider(
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Check local Ollama availability without sending conversation evidence."""

    try:
        from analyzazprav.a5_ai.providers import (
            OllamaProvider,
            ProviderError,
            ProviderTimeout,
            ProviderUnavailable,
        )
    except ImportError as exc:
        raise RuntimeUnavailable("Lokální AI provider není v aktuálním checkoutu nainstalovaný.") from exc

    provider = OllamaProvider(
        model_name,
        base_url=base_url,
        preflight_timeout_seconds=timeout_seconds,
    )
    try:
        result = provider.preflight()
    except ProviderTimeout as exc:
        return {
            "status": "timeout",
            "provider": "ollama",
            "model": model_name,
            "base_url": base_url.rstrip("/"),
            "error": str(exc),
        }
    except ProviderUnavailable as exc:
        return {
            "status": "unavailable",
            "provider": "ollama",
            "model": model_name,
            "base_url": base_url.rstrip("/"),
            "error": str(exc),
        }
    except ProviderError as exc:
        return {
            "status": "invalid_response",
            "provider": "ollama",
            "model": model_name,
            "base_url": base_url.rstrip("/"),
            "error": str(exc),
        }

    payload = result.to_dict()
    return {
        "status": "ready",
        "provider": payload["provider"],
        "model": payload["requested_model"],
        "base_url": payload["base_url"],
        "available_models": payload["available_models"],
        "error": None,
    }


def default_a5_cache_path() -> Path:
    """Compatibility helper retained while the old A5 cache is retired."""

    configured = os.environ.get("ANALYZA_ZPRAV_A5_CACHE")
    path = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".datadata" / "cache" / "a5.sqlite"
    )
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_local_runtime(
    packet: Mapping[str, Any],
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    user_question: str | None = None,
    inference_timeout_seconds: float = 300.0,
    max_input_chars: int = 6000,
) -> dict[str, Any]:
    """Run the authoritative Runtime v2 through local Ollama only.

    Identity/provenance and provider-size budget are validated before any message
    text reaches the provider. Ollama receives strict JSON Schema, thinking is
    disabled, output length is bounded, and each pack gets exactly one inference
    call. Canonical/source evidence is materialized locally after validation.
    """

    try:
        from analyzazprav.a5_ai.providers import OllamaProvider
        from analyzazprav.runtime import OUTPUT_SCHEMA, analyze_packet, compile_packet_to_packs
    except ImportError as exc:
        raise RuntimeUnavailable("Runtime v2 není v aktuálním checkoutu nainstalovaný.") from exc

    compile_packet_to_packs(
        packet,
        question=user_question,
        max_input_chars=max_input_chars,
    )

    provider = OllamaProvider(
        model_name,
        base_url=base_url,
        timeout_seconds=inference_timeout_seconds,
        response_format=OUTPUT_SCHEMA,
        think=False,
        temperature=0.0,
        num_predict=768,
    )
    provider.preflight()

    return analyze_packet(
        packet,
        provider=provider,
        question=user_question,
        max_input_chars=max_input_chars,
    )


def run_local_a5(
    packet: Mapping[str, Any],
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    analysis_type: str = "segment",
    mode: str = "blind",
    user_question: str | None = None,
    force_refresh: bool = False,
    cache_path: str | Path | None = None,
    inference_timeout_seconds: float = 300.0,
    max_input_chars: int = 6000,
) -> dict[str, Any]:
    """Deprecated compatibility adapter around Runtime v2.

    Historical A5-only arguments are ignored. New code must call
    ``run_local_runtime`` directly.
    """

    del analysis_type, mode, force_refresh, cache_path
    try:
        from analyzazprav.runtime import to_legacy_execution
    except ImportError as exc:
        raise RuntimeUnavailable("Runtime v2 není v aktuálním checkoutu nainstalovaný.") from exc

    result = run_local_runtime(
        packet,
        model_name=model_name,
        base_url=base_url,
        user_question=user_question,
        inference_timeout_seconds=inference_timeout_seconds,
        max_input_chars=max_input_chars,
    )
    return to_legacy_execution(result)
