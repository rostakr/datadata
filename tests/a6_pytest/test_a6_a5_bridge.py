from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from a6.a5_bridge import (
    a5_available,
    check_local_a5_provider,
    default_a5_cache_path,
    run_local_a5,
)
from a6.data import analysis_packet, demo_messages


def test_a5_available_returns_boolean():
    assert isinstance(a5_available(), bool)


def test_run_local_a5_validates_before_preflight_then_uses_chunk_orchestrator(monkeypatch, tmp_path):
    package = ModuleType("analyzazprav")
    a5 = ModuleType("analyzazprav.a5_ai")
    providers = ModuleType("analyzazprav.a5_ai.providers")
    calls = []

    class FakePacketSource:
        @classmethod
        def from_packet(cls, packet):
            assert packet["schema_version"] == 1
            calls.append("packet")
            return cls()

    def fake_candidate(packet):
        assert packet["schema_version"] == 1
        calls.append("candidate")
        return "candidate"

    class FakeCache:
        def __init__(self, path):
            calls.append("cache")
            assert Path(path) == tmp_path / "a5.sqlite"

    class FakeProvider:
        def __init__(self, model_name, *, base_url, timeout_seconds=120.0, preflight_timeout_seconds=5.0):
            assert model_name == "test-model"
            assert base_url == "http://localhost:11434"
            assert timeout_seconds == 900.0
            self.model_name = model_name
            self.base_url = base_url

        def preflight(self):
            calls.append("preflight")
            return SimpleNamespace(
                to_dict=lambda: {
                    "provider": "ollama",
                    "base_url": self.base_url,
                    "requested_model": self.model_name,
                    "available_models": [self.model_name],
                    "ready": True,
                }
            )

    class FakeExecution:
        def to_dict(self):
            return {
                "status": "completed",
                "context_hash": "hash-1",
                "error": None,
                "result": {"summary": "ok", "overall_confidence": 0.9},
                "chunking": {
                    "enabled": True,
                    "chunk_count": 2,
                    "selected_message_count": 121,
                    "evidence_chunk_size": 120,
                    "synthesis_used": True,
                    "synthesis_status": "completed",
                    "chunks": [],
                },
            }

    def fake_chunked(
        packet,
        *,
        provider,
        analysis_type,
        mode,
        user_question,
        cache,
        force_refresh,
    ):
        calls.append("analyze")
        assert isinstance(provider, FakeProvider)
        assert isinstance(cache, FakeCache)
        assert analysis_type == "segment"
        assert mode == "blind"
        assert user_question == "question"
        assert force_refresh is True
        return FakeExecution()

    a5.A6PacketMessageSource = FakePacketSource
    a5.AnalysisCache = FakeCache
    a5.AnalysisMode = lambda value: value
    a5.AnalysisType = lambda value: value
    a5.analyze_a6_packet_chunked = fake_chunked
    a5.candidate_from_a6_packet = fake_candidate
    providers.OllamaProvider = FakeProvider

    monkeypatch.setitem(sys.modules, "analyzazprav", package)
    monkeypatch.setitem(sys.modules, "analyzazprav.a5_ai", a5)
    monkeypatch.setitem(sys.modules, "analyzazprav.a5_ai.providers", providers)

    execution = run_local_a5(
        {"schema_version": 1},
        model_name="test-model",
        analysis_type="segment",
        mode="blind",
        user_question="question",
        force_refresh=True,
        cache_path=tmp_path / "a5.sqlite",
        inference_timeout_seconds=900.0,
    )
    assert execution["status"] == "completed"
    assert execution["chunking"]["chunk_count"] == 2
    assert calls.index("packet") < calls.index("preflight")
    assert calls.index("candidate") < calls.index("preflight")
    assert calls.index("preflight") < calls.index("analyze")


def test_default_a5_cache_path_is_private_and_configurable(monkeypatch, tmp_path):
    configured = tmp_path / "private-cache" / "a5.sqlite"
    monkeypatch.setenv("ANALYZA_ZPRAV_A5_CACHE", str(configured))

    path = default_a5_cache_path()

    assert path == configured.resolve()
    assert path.parent.is_dir()


def test_check_local_a5_provider_returns_structured_ready_status(monkeypatch):
    package = ModuleType("analyzazprav")
    a5 = ModuleType("analyzazprav.a5_ai")
    providers = ModuleType("analyzazprav.a5_ai.providers")

    class ProviderError(RuntimeError):
        pass

    class ProviderUnavailable(ProviderError):
        pass

    class ProviderTimeout(ProviderError):
        pass

    class FakeProvider:
        def __init__(self, model_name, *, base_url, preflight_timeout_seconds):
            assert preflight_timeout_seconds == 2.0
            self.model_name = model_name
            self.base_url = base_url.rstrip("/")

        def preflight(self):
            return SimpleNamespace(
                to_dict=lambda: {
                    "provider": "ollama",
                    "base_url": self.base_url,
                    "requested_model": self.model_name,
                    "available_models": [self.model_name],
                    "ready": True,
                }
            )

    providers.OllamaProvider = FakeProvider
    providers.ProviderError = ProviderError
    providers.ProviderUnavailable = ProviderUnavailable
    providers.ProviderTimeout = ProviderTimeout

    monkeypatch.setitem(sys.modules, "analyzazprav", package)
    monkeypatch.setitem(sys.modules, "analyzazprav.a5_ai", a5)
    monkeypatch.setitem(sys.modules, "analyzazprav.a5_ai.providers", providers)

    status = check_local_a5_provider(
        model_name="test-model",
        base_url="http://localhost:11434/",
        timeout_seconds=2.0,
    )
    assert status == {
        "status": "ready",
        "provider": "ollama",
        "model": "test-model",
        "base_url": "http://localhost:11434",
        "available_models": ["test-model"],
        "error": None,
    }


def test_real_a5_accepts_current_a6_packet_when_package_is_composed():
    """Composition contract test.

    This intentionally skips on the standalone A6 branch where A5 is not yet
    installed. In an A6-over-A5 merge-ref it must execute against the real A5
    adapter and therefore turns package/API drift into a CI failure.
    """
    a5 = pytest.importorskip("analyzazprav.a5_ai")

    frame = demo_messages()
    selected_id = str(frame.iloc[5].message_id)
    packet = analysis_packet(frame, [selected_id], context_before=2, context_after=2)

    source = a5.A6PacketMessageSource.from_packet(packet)
    candidate = a5.candidate_from_a6_packet(packet)
    request = a5.request_from_a6_packet(
        packet,
        analysis_type=a5.AnalysisType.SEGMENT,
        mode=a5.AnalysisMode.BLIND,
        user_question="composition-check",
    )

    assert len(source.messages) == packet["message_count"]
    assert candidate.conversation_id == frame.iloc[5].conversation_id
    assert candidate.evidence_message_ids == (selected_id,)
    assert request.conversation_id == candidate.conversation_id
    assert request.candidate_id == candidate.id
    assert request.user_question == "composition-check"
