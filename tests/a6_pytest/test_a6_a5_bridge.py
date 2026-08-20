from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_run_local_a5_uses_runtime_v2_single_call_and_local_materialization(monkeypatch):
    from analyzazprav.a5_ai import providers
    from analyzazprav.runtime import OUTPUT_SCHEMA

    calls: list[str] = []

    class FakeProvider:
        def __init__(
            self,
            model_name,
            *,
            base_url,
            timeout_seconds=120.0,
            preflight_timeout_seconds=5.0,
            response_format="json",
            think=None,
            temperature=None,
            num_predict=None,
        ):
            assert model_name == "test-model"
            assert base_url == "http://localhost:11434"
            assert timeout_seconds == 900.0
            assert response_format == OUTPUT_SCHEMA
            assert think is False
            assert temperature == 0.0
            assert num_predict == 768
            self._model_name = model_name
            calls.append("init")

        @property
        def provider_name(self):
            return "ollama"

        @property
        def model_name(self):
            return self._model_name

        def preflight(self):
            calls.append("preflight")
            return SimpleNamespace(ready=True)

        def analyze(self, *, system_prompt, user_prompt):
            calls.append("analyze")
            assert "source_record" not in user_prompt
            assert "membership_id" not in user_prompt
            assert '"label":"E1"' in user_prompt
            return {
                "summary": "Stručný souhrn",
                "claims": [
                    {
                        "kind": "observation",
                        "text": "Pozorování",
                        "evidence": ["E1"],
                        "confidence": "medium",
                    }
                ],
            }

    monkeypatch.setattr(providers, "OllamaProvider", FakeProvider)

    frame = demo_messages()
    selected_id = str(frame.iloc[5].message_id)
    packet = analysis_packet(frame, [selected_id], context_before=0, context_after=0)
    execution = run_local_a5(
        packet,
        model_name="test-model",
        user_question="question",
        force_refresh=True,
        inference_timeout_seconds=900.0,
    )

    assert execution["status"] == "completed"
    assert execution["runtime_schema"] == "runtime-v2-1"
    assert execution["result"]["observations"][0]["evidence"]["message_ids"] == [selected_id]
    assert calls == ["init", "preflight", "analyze"]


def test_default_a5_cache_path_is_private_and_configurable(monkeypatch, tmp_path):
    configured = tmp_path / "private-cache" / "a5.sqlite"
    monkeypatch.setenv("ANALYZA_ZPRAV_A5_CACHE", str(configured))

    path = default_a5_cache_path()

    assert path == configured.resolve()
    assert path.parent.is_dir()


def test_check_local_a5_provider_returns_structured_ready_status(monkeypatch):
    from analyzazprav.a5_ai import providers

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

    monkeypatch.setattr(providers, "OllamaProvider", FakeProvider)

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


def test_runtime_v2_accepts_current_a6_packet_when_package_is_composed():
    runtime = pytest.importorskip("analyzazprav.runtime")

    frame = demo_messages()
    selected_id = str(frame.iloc[5].message_id)
    packet = analysis_packet(frame, [selected_id], context_before=2, context_after=2)

    packs = runtime.compile_packet_to_packs(packet, question="composition-check")

    assert len(packs) == 1
    assert any(item.message_id == selected_id for item in packs[0].items)
    provider_payload = packs[0].provider_payload()
    assert provider_payload["question"] == "composition-check"
    assert all("message_id" not in item for item in provider_payload["evidence"])
