from __future__ import annotations

from analyzazprav.runtime import AnalysisStore, compile_packet_to_packs, result_fingerprint


def _packet(message_id: str = "m1", membership_id: str = "mem1"):
    return {
        "schema_version": 1,
        "selected_message_ids": [message_id],
        "source_provenance_required": True,
        "source_provenance_status": "complete",
        "messages": [
            {
                "message_id": message_id,
                "membership_id": membership_id,
                "conversation_id": "c1",
                "sender": "p1",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "text": "same text",
                "source_record_keys": ["record"],
                "source_snapshot_keys": ["snapshot"],
                "source_parser_versions": ["parser"],
                "source_provenance_status": "complete",
            }
        ],
    }


def test_analysis_store_round_trip_is_local_sqlite(tmp_path):
    path = tmp_path / "runtime.sqlite"
    store = AnalysisStore(path)
    packs = compile_packet_to_packs(_packet())
    key = result_fingerprint(packs, provider="ollama", model="tiny")
    result = {"status": "COMPLETED", "summary": "ok", "claims": []}

    assert store.get(key) is None
    store.put(key, result, provider="ollama", model="tiny")

    assert path.is_file()
    assert store.get(key) == result


def test_fingerprint_includes_private_canonical_mapping_not_just_visible_text():
    first = compile_packet_to_packs(_packet("m1", "mem1"))
    second = compile_packet_to_packs(_packet("m2", "mem2"))

    assert first[0].provider_payload() == second[0].provider_payload()
    assert result_fingerprint(first, provider="ollama", model="tiny") != result_fingerprint(
        second, provider="ollama", model="tiny"
    )


def test_fingerprint_changes_with_model():
    packs = compile_packet_to_packs(_packet())

    assert result_fingerprint(packs, provider="ollama", model="tiny-a") != result_fingerprint(
        packs, provider="ollama", model="tiny-b"
    )
