from __future__ import annotations

from argparse import Namespace
import json
import sqlite3
from types import SimpleNamespace

from tools import runtime_live_acceptance as cli


MESSAGE_ID = "private-message-id"
MEMBERSHIP_ID = "private-membership-id"
CONVERSATION_ID = "private-conversation-id"
SOURCE_RECORD = "private-source-record"
SOURCE_SNAPSHOT = "private-source-snapshot"
PRIVATE_TEXT = "private synthetic text"


def _database(tmp_path):
    path = tmp_path / "messages.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE analysis_messages (
            membership_id TEXT NOT NULL,
            id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            sender_name TEXT,
            sent_at_utc_us INTEGER,
            timestamp_precision TEXT,
            timestamp_quality TEXT,
            text TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO analysis_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            MEMBERSHIP_ID,
            MESSAGE_ID,
            CONVERSATION_ID,
            "p1",
            1785542400000000,
            "microsecond",
            "exact",
            PRIVATE_TEXT,
        ),
    )
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
        "INSERT INTO analysis_message_sources VALUES (?, ?, ?, ?)",
        (MESSAGE_ID, SOURCE_RECORD, SOURCE_SNAPSHOT, "private-run"),
    )
    conn.commit()
    conn.close()
    return path


def _packet(tmp_path):
    path = tmp_path / "packet.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected_message_ids": [MESSAGE_ID],
                "source_provenance_required": True,
                "source_provenance_status": "complete",
                "messages": [
                    {
                        "message_id": MESSAGE_ID,
                        "membership_id": MEMBERSHIP_ID,
                        "conversation_id": CONVERSATION_ID,
                        "sender": "p1",
                        "timestamp": "2026-08-01T00:00:00+00:00",
                        "text": PRIVATE_TEXT,
                        "source_record_keys": [SOURCE_RECORD],
                        "source_snapshot_keys": [SOURCE_SNAPSHOT],
                        "source_parser_versions": [],
                        "source_provenance_status": "complete",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _args(tmp_path):
    return Namespace(
        database=str(_database(tmp_path)),
        packet=str(_packet(tmp_path)),
        model="test-model",
        base_url="http://localhost:11434",
        timeout_seconds=300.0,
        max_input_chars=6000,
        question=None,
    )


class GoodProvider:
    def __init__(self, model_name, **kwargs):
        self._model_name = model_name
        self.kwargs = kwargs

    @property
    def provider_name(self):
        return "ollama"

    @property
    def model_name(self):
        return self._model_name

    def preflight(self):
        return SimpleNamespace(ready=True)

    def analyze(self, *, system_prompt, user_prompt):
        assert PRIVATE_TEXT in user_prompt
        assert MESSAGE_ID not in user_prompt
        assert MEMBERSHIP_ID not in user_prompt
        assert SOURCE_RECORD not in user_prompt
        return {
            "summary": "summary",
            "claims": [
                {
                    "kind": "observation",
                    "text": "claim",
                    "evidence": ["E1"],
                    "confidence": "medium",
                }
            ],
        }


def test_runtime_live_acceptance_passes_and_report_is_privacy_safe(monkeypatch, tmp_path):
    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.setattr(cli, "OllamaProvider", GoodProvider)

    report = cli.run(_args(tmp_path))

    assert report["verdict"] == "PASS"
    assert report["pack_count"] == 1
    assert report["claim_count"] == 1
    assert report["reconciliation"] == {
        "PASS": 1,
        "STALE": 0,
        "FAIL": 0,
        "UNVERIFIED": 0,
    }
    serialized = json.dumps(report, ensure_ascii=False)
    for private in (
        MESSAGE_ID,
        MEMBERSHIP_ID,
        CONVERSATION_ID,
        SOURCE_RECORD,
        SOURCE_SNAPSHOT,
        PRIVATE_TEXT,
        str(tmp_path),
    ):
        assert private not in serialized


def test_runtime_live_acceptance_fails_closed_on_invalid_model_label(monkeypatch, tmp_path):
    class BadProvider(GoodProvider):
        def analyze(self, *, system_prompt, user_prompt):
            return {
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

    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.setattr(cli, "OllamaProvider", BadProvider)

    report = cli.run(_args(tmp_path))

    assert report["verdict"] == "FAIL"
    assert report["failure_reasons"] == ["MODEL_OUTPUT_INVALID"]


def test_runtime_live_acceptance_refuses_codespaces_before_private_file_read(monkeypatch, tmp_path):
    monkeypatch.setenv("CODESPACES", "true")
    args = Namespace(
        database="/private/does-not-need-to-exist.sqlite",
        packet="/private/does-not-need-to-exist.json",
        model="test-model",
        base_url="http://localhost:11434",
        timeout_seconds=300.0,
        max_input_chars=6000,
        question=None,
    )

    report = cli.run(args)

    assert report["verdict"] == "FAIL"
    assert report["failure_reasons"] == ["UNTRUSTED_RUNTIME"]
