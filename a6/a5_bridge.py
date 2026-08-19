from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


class A5Unavailable(RuntimeError):
    pass


def a5_available() -> bool:
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
    """Check local Ollama availability without sending conversation evidence."""

    try:
        from analyzazprav.a5_ai.providers import (
            OllamaProvider,
            ProviderError,
            ProviderTimeout,
            ProviderUnavailable,
        )
    except ImportError as exc:
        raise A5Unavailable("Lokální AI provider není v aktuálním checkoutu nainstalovaný.") from exc

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
    inference_timeout_seconds: float = 120.0,
    max_input_chars: int = 6000,
) -> dict[str, Any]:
    """Run Runtime v2 through local Ollama only.

    This function keeps the historical A6 call signature during migration, but
    the old A5 orchestrator is no longer used. Runtime v2 validates and budgets
    evidence before provider work, sends only compact E-label evidence to one
    inference call per pack, performs no automatic repair call, and materializes
    canonical/provenance evidence locally after inference.

    ``analysis_type``, ``mode``, ``force_refresh`` and ``cache_path`` are accepted
    only for temporary UI/API compatibility and do not change the Runtime v2
    contract.
    """

    del analysis_type, mode, force_refresh, cache_path

    try:
        from analyzazprav.a5_ai.providers import OllamaProvider
        from analyzazprav.runtime import (
            analyze_packet,
            compile_packet_to_packs,
            to_legacy_execution,
        )
    except ImportError as exc:
        raise A5Unavailable("Runtime v2 není v aktuálním checkoutu nainstalovaný.") from exc

    # Validate provenance/identity and enforce the evidence budget before any
    # provider/network call can receive conversation text.
    compile_packet_to_packs(
        packet,
        question=user_question,
        max_input_chars=max_input_chars,
    )

    provider = OllamaProvider(
        model_name,
        base_url=base_url,
        timeout_seconds=inference_timeout_seconds,
    )
    provider.preflight()

    runtime_result = analyze_packet(
        packet,
        provider=provider,
        question=user_question,
        max_input_chars=max_input_chars,
    )
    return to_legacy_execution(runtime_result)
