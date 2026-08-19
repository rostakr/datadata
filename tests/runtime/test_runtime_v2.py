from __future__ import annotations

import json

import pytest

from analyzazprav.runtime import (
    RuntimeValidationError,
    analyze_packet,
    build_user_prompt,
    compile_packet_to_packs,
    interpret_pack,
)


def packet(*, texts=None, selected=None):
    texts = texts or ["a", "b", "c", "d"]
    messages = []
    for index, text in enumerate(texts, start=1):
        messages.append(
            {
                "message_id": f"m{index}",
                "membership_id": f"mem{index}",
                "conversation_id": "c1",
                "sender": "p1" if index % 2 else "p2",
                "timestamp": f"2026-01-01T00:0{index}:00+00:00",
                "text": text,
                "source_record_keys": [f"r{index}"],
                "source_snapshot_keys": ["snapshot"],
                "source_parser_versions": ["parser"],
                "source_provenance_status": "complete",
            }
        )
    selected = selected or ["m2", "m3"]
    return {
        "schema_version": 1,
        "selected_message_ids": selected,
        "messages": messages,
        "source_provenance_required": True,
        "source_provenance_status": "complete",
    }


class FakeProvider:
    provider_name = "fake"
    model_name = "tiny"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def analyze(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.response


def test_provider_payload_never_contains_canonical_or_source_identity():
    pack = compile_packet_to_packs(packet(), question="co se děje?")[0]
    payload = build_user_prompt(pack)

    assert '"label":"E1"' in payload
    assert "message_id" not in payload
    assert "membership_id" not in payload
    assert "source_record_keys" not in payload
    assert "source_snapshot_keys" not in payload
    assert "r1" not in payload
    assert "snapshot" not in payload


def test_selected_messages_are_losslessly_partitioned_by_real_payload_budget():
    source = packet(texts=["x" * 900, "y" * 900, "z" * 900, "w" * 900], selected=["m1", "m2", "m3", "m4"])

    packs = compile_packet_to_packs(source, max_input_chars=2200)

    selected_ids = {"m1", "m2", "m3", "m4"}
    covered = {
        item.message_id
        for evidence_pack in packs
        for item in evidence_pack.items
        if item.message_id in selected_ids
    }
    assert covered == selected_ids
    assert len(packs) >= 2
    assert all(len(build_user_prompt(evidence_pack)) <= 2200 for evidence_pack in packs)


def test_invalid_model_label_fails_once_without_repair():
    pack = compile_packet_to_packs(packet(), max_input_chars=6000)[0]
    provider = FakeProvider(
        {
            "summary": "summary",
            "claims": [
                {
                    "kind": "observation",
                    "text": "claim",
                    "evidence": ["E999"],
                    "confidence": "medium",
                }
            ],
        }
    )

    with pytest.raises(RuntimeValidationError, match="unknown labels"):
        interpret_pack(pack, provider=provider)

    assert len(provider.calls) == 1


def test_service_materializes_provenance_locally_after_valid_inference():
    provider = FakeProvider(
        {
            "summary": "summary",
            "claims": [
                {
                    "kind": "interpretation",
                    "text": "claim",
                    "evidence": ["E1"],
                    "confidence": "high",
                }
            ],
        }
    )

    result = analyze_packet(packet(), provider=provider, max_input_chars=6000)

    assert result["schema_version"] == "runtime-v2-1"
    assert result["status"] == "COMPLETED"
    assert len(provider.calls) == result["pack_count"] == 1
    claim = result["claims"][0]
    assert claim["evidence"]["message_ids"]
    snapshot = claim["evidence"]["messages"][0]
    assert snapshot["membership_id"]
    assert snapshot["source_record_keys"]
    sent = json.loads(provider.calls[0][1])
    assert all("membership_id" not in item for item in sent["evidence"])


def test_mixed_conversation_and_incomplete_provenance_fail_before_inference():
    mixed = packet()
    mixed["messages"][0]["conversation_id"] = "other"
    with pytest.raises(RuntimeValidationError, match="multiple conversations"):
        compile_packet_to_packs(mixed)

    incomplete = packet()
    incomplete["messages"][0]["source_record_keys"] = []
    with pytest.raises(RuntimeValidationError, match="complete required source provenance"):
        compile_packet_to_packs(incomplete)
