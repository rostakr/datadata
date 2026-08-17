from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


class A5Unavailable(RuntimeError):
    pass


def a5_available() -> bool:
    try:
        import analyzazprav.a5_ai  # noqa: F401
    except ImportError:
        return False
    return True


def check_local_a5_provider(
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Check local Ollama availability without sending any A5 evidence context."""

    try:
        from analyzazprav.a5_ai.providers import (
            OllamaProvider,
            ProviderError,
            ProviderTimeout,
            ProviderUnavailable,
        )
    except ImportError as exc:
        raise A5Unavailable("A5 modul není v aktuálním checkoutu nainstalovaný.") from exc

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
    """Return the private local A5 cache path outside the public repository."""

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
) -> dict[str, Any]:
    """Run A5 explicitly through local Ollama only.

    Production A6 packet/provenance validation happens before provider/network
    work. Ollama preflight then verifies the exact local model via ``/api/tags``
    before any evidence reaches ``/api/chat``. Large explicit selections are
    deterministically chunked and synthesized by A5; no cloud fallback exists.
    """

    try:
        from analyzazprav.a5_ai import (
            A6PacketMessageSource,
            AnalysisCache,
            AnalysisMode,
            AnalysisType,
            analyze_a6_packet_chunked,
            candidate_from_a6_packet,
        )
        from analyzazprav.a5_ai.providers import OllamaProvider
    except ImportError as exc:
        raise A5Unavailable("A5 modul není v aktuálním checkoutu nainstalovaný.") from exc

    # Fail closed on packet/membership/source provenance before provider/network work.
    A6PacketMessageSource.from_packet(packet)
    candidate_from_a6_packet(packet)

    provider = OllamaProvider(model_name, base_url=base_url)
    # /api/tags carries model inventory only; no evidence or message text.
    provider.preflight()

    local_cache = Path(cache_path).expanduser().resolve() if cache_path else default_a5_cache_path()
    local_cache.parent.mkdir(parents=True, exist_ok=True)
    cache = AnalysisCache(local_cache)

    execution = analyze_a6_packet_chunked(
        packet,
        provider=provider,
        analysis_type=AnalysisType(analysis_type),
        mode=AnalysisMode(mode),
        user_question=user_question or None,
        cache=cache,
        force_refresh=force_refresh,
    )
    return execution.to_dict()
