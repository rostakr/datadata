from __future__ import annotations

import json
import sqlite3

from a6.live_acceptance import build_live_acceptance_report
from tools import a5_live_acceptance as cli


MESSAGE_ID = "private-message-id-001"
MEMBERSHIP_ID = "private-membership-id-001"
CONVERSATION_ID = "private-conversation-id-001"
SOURCE_RECORD = "private-source-record-key-001"
SOURCE_SNAPSHOT = "private-source-snapshot-key-001"
PRIVATE_TEXT = "very private synthetic message text"


def _database(tmp_path, *, snapshot_key: str = SOURCE_SNAPSHOT):
    path = tmp_path / "messages.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE analysis_message_sources (
            message_id TEXT NOT NULL,
            source_record_key TEXT,
            source_snapshot_key TEXT,
            import_run_id TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO analysis_message_sources(message_id, source_record_key, source_snapshot_key, import_run_id) "
        "VALUES (?, ?, ?, ?)",
        (MESSAGE_ID, SOURCE_RECORD, snapshot_key, "private-run-id"),
    )
    conn.commit()
    conn.close()
    return path


def _packet():
    return {
        "schema_version": 1,
        "selected_message_ids": [MESSAGE_ID],
        "messages": [
            {
                "message_id": MESSAGE_ID,
                "membership_id": MEMBERSHIP_ID,
                "conversation_id": CONVERSATION_ID,
                "text": PRIVATE_TEXT,
            }
        ],
    }


def _execution(*, materialized: bool = True, chunk_statuses=("completed",)):
    summary_evidence = {
        "message_ids": [MESSAGE_ID],
        "description": PRIVATE_TEXT,
    }
    if materialized:
        summary_evidence["messages"] = [
            {
                "message_id": MESSAGE_ID,
                "membership_id": MEMBERSHIP_ID,
                "timestamp": "2026-08-01T00:00:00+00:00",
                "sender_id": "private-sender-id",
                "excerpt": PRIVATE_TEXT,
                "source_record_keys": [SOURCE_RECORD],
                "source_snapshot_keys": [SOURCE_SNAPSHOT],
                "source_parser_versions": [],
            }
        ]
        summary_evidence["metrics"] = []

    return {
        "status": "completed",
        "context_hash": "private-context-hash",
        "error": None,
        "result": {
            "summary": PRIVATE_TEXT,
            "summary_evidence": summary_evidence,
            "observations": [],
            "interpretations": [],
            "patterns": [],
            "turning_point_evidence": [],
            "overall_confidence": 0.9,
        },
        "chunking": {
            "enabled": len(chunk_statuses) > 1,
            "selected_message_count": 1,
            "evidence_chunk_size": 120,
            "chunk_count": len(chunk_statuses),
            "synthesis_used": len(chunk_statuses) > 1,
            "synthesis_status": "completed" if all(status == "completed" for status in chunk_statuses) else "failed",
            "chunks": [
                {
                    "chunk_index": index,
                    "evidence_count": 1,
                    "status": status,
                    "context_hash": f"private-chunk-hash-{index}",
                    "error": None,
                }
                for index, status in enumerate(chunk_statuses, start=1)
            ],
        },
    }


def test_live_acceptance_passes_and_report_is_privacy_safe(tmp_path):
    report = build_live_acceptance_report(
        _execution(),
        _packet(),
        database=_database(tmp_path),
        model_name="qwen3:8b",
    )

    assert report["verdict"] == "PASS"
    assert report["fresh_inference_required"] is True
    assert report["reconciliation"] == {
        "PASS": 1,
        "STALE": 0,
        "FAIL": 0,
        "UNVERIFIED": 0,
    }
    assert report["failure_reasons"] == []

    serialized = json.dumps(report, ensure_ascii=False)
    for private_value in (
        MESSAGE_ID,
        MEMBERSHIP_ID,
        CONVERSATION_ID,
        SOURCE_RECORD,
        SOURCE_SNAPSHOT,
        PRIVATE_TEXT,
        "private-context-hash",
        "private-sender-id",
        "private-run-id",
        str(tmp_path),
    ):
        assert private_value not in serialized


def test_live_acceptance_fails_closed_on_source_provenance_drift(tmp_path):
    report = build_live_acceptance_report(
        _execution(),
        _packet(),
        database=_database(tmp_path, snapshot_key="different-current-snapshot"),
        model_name="qwen3:8b",
    )

    assert report["verdict"] == "FAIL"
    assert report["reconciliation"]["STALE"] == 1
    assert "EVIDENCE_RECONCILIATION_NOT_PASS" in report["failure_reasons"]


def test_live_acceptance_fails_closed_without_materialized_evidence(tmp_path):
    report = build_live_acceptance_report(
        _execution(materialized=False),
        _packet(),
        database=_database(tmp_path),
        model_name="qwen3:8b",
    )

    assert report["verdict"] == "FAIL"
    assert report["reconciliation"]["UNVERIFIED"] == 1
    assert "EVIDENCE_RECONCILIATION_NOT_PASS" in report["failure_reasons"]


def test_live_acceptance_fails_closed_when_any_chunk_is_not_completed(tmp_path):
    report = build_live_acceptance_report(
        _execution(chunk_statuses=("completed", "failed")),
        _packet(),
        database=_database(tmp_path),
        model_name="qwen3:8b",
    )

    assert report["verdict"] == "FAIL"
    assert report["chunk_count"] == 2
    assert report["completed_chunk_count"] == 1
    assert "CHUNK_NOT_COMPLETED" in report["failure_reasons"]


def test_cli_forces_fresh_inference(monkeypatch):
    packet = _packet()
    execution = _execution()
    calls = {}

    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.setattr(cli, "_load_packet", lambda path: packet)
    monkeypatch.setattr(
        cli,
        "enrich_analysis_packet_source_provenance",
        lambda payload, database, require_provenance: payload,
    )

    def fake_run_local_a5(
        payload,
        *,
        model_name,
        base_url,
        analysis_type,
        mode,
        force_refresh,
    ):
        calls["force_refresh"] = force_refresh
        assert payload is packet
        assert model_name == "test-model"
        assert base_url == "http://localhost:11434"
        assert analysis_type == "segment"
        assert mode == "blind"
        return execution

    monkeypatch.setattr(cli, "run_local_a5", fake_run_local_a5)
    monkeypatch.setattr(
        cli,
        "build_live_acceptance_report",
        lambda result, payload, *, database, model_name: {
            "schema_version": "a5-live-acceptance-v1",
            "verdict": "PASS",
        },
    )

    rc = cli.main(
        [
            "--database",
            "/private/messages.sqlite",
            "--packet",
            "/private/a5-context.json",
            "--model",
            "test-model",
        ]
    )

    assert rc == 0
    assert calls["force_refresh"] is True
