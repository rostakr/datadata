from __future__ import annotations

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


def run_local_a5(
    packet: Mapping[str, Any],
    *,
    model_name: str,
    base_url: str = "http://localhost:11434",
    analysis_type: str = "segment",
    mode: str = "blind",
    user_question: str | None = None,
) -> dict[str, Any]:
    """Run A5 explicitly through local Ollama only.

    The A5 packet adapter validates membership and source provenance before the
    provider is constructed. The provider then verifies the local Ollama server
    and exact requested model via ``/api/tags`` before any evidence prompt can be
    sent to ``/api/chat``. No cloud fallback is attempted.
    """

    try:
        from analyzazprav.a5_ai import (
            A6PacketMessageSource,
            AIAnalyzer,
            AnalysisMode,
            AnalysisType,
            ContextBuilder,
            candidate_from_a6_packet,
            request_from_a6_packet,
        )
        from analyzazprav.a5_ai.providers import OllamaProvider
    except ImportError as exc:
        raise A5Unavailable("A5 modul není v aktuálním checkoutu nainstalovaný.") from exc

    # All packet/provenance validation happens before local provider/network work.
    source = A6PacketMessageSource.from_packet(packet)
    candidate = candidate_from_a6_packet(packet)
    request = request_from_a6_packet(
        packet,
        analysis_type=AnalysisType(analysis_type),
        mode=AnalysisMode(mode),
        user_question=user_question or None,
    )
    provider = OllamaProvider(model_name, base_url=base_url)
    # Fail closed before /api/chat. /api/tags carries no evidence or message text.
    provider.preflight()
    analyzer = AIAnalyzer(
        context_builder=ContextBuilder(source),
        provider=provider,
        cache=None,
    )
    execution = analyzer.analyze(request, candidate)
    return {
        "status": execution.status.value,
        "context_hash": execution.context_hash,
        "error": execution.error,
        "result": execution.result.to_dict() if execution.result is not None else None,
    }
