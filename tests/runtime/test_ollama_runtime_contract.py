from __future__ import annotations

import json

from analyzazprav.a5_ai.providers import OllamaProvider
from analyzazprav.runtime import OUTPUT_SCHEMA


def test_runtime_ollama_payload_uses_schema_disables_thinking_and_bounds_output(monkeypatch):
    provider = OllamaProvider(
        "qwen3:1.7b",
        response_format=OUTPUT_SCHEMA,
        think=False,
        temperature=0.0,
        num_predict=768,
        timeout_seconds=300.0,
    )
    captured = {}

    def fake_read_json(request, *, timeout_seconds):
        captured["timeout_seconds"] = timeout_seconds
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return {
            "message": {
                "content": json.dumps(
                    {
                        "summary": "ok",
                        "claims": [
                            {
                                "kind": "observation",
                                "text": "ok",
                                "evidence": ["E1"],
                                "confidence": "medium",
                            }
                        ],
                    }
                )
            }
        }

    monkeypatch.setattr(provider, "_read_json", fake_read_json)

    result = provider.analyze(system_prompt="system", user_prompt='{"evidence":[]}')

    assert result["summary"] == "ok"
    assert captured["timeout_seconds"] == 300.0
    payload = captured["payload"]
    assert payload["format"] == OUTPUT_SCHEMA
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.0, "num_predict": 768}
