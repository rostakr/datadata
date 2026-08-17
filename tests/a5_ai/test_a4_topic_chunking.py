from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

import pytest

from analyzazprav.a5_ai.context_builder import ContextBuilder
from analyzazprav.a5_ai.integration_a2 import A2SQLiteMessageSource
from analyzazprav.a5_ai.integration_a4_sqlite import (
    A4SQLiteCandidateSource,
    A4SQLiteSourceError,
    LEXICAL_TOPIC_EVIDENCE_CHUNK_SIZE,
)
from analyzazprav.a5_ai.models import AIAnalysisRequest, AnalysisMode, AnalysisType


UTC = timezone.utc
BASE_US = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1_000_000)


def _database(tmp_path: Path, *, message_count: int, evidence_ids: list[int]) -> Path:
    database = tmp_path / "messages.sqlite"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE analysis_messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                sender_id INTEGER,
                sent_at_utc_us INTEGER,
                message_type TEXT,
                text TEXT
            );
            CREATE TABLE topic_rows (
                conversation_id INTEGER NOT NULL,
                topic_key TEXT NOT NULL,
                method TEXT NOT NULL,
                normalized_phrase TEXT NOT NULL,
                ngram_size INTEGER NOT NULL,
                document_frequency INTEGER NOT NULL,
                document_frequency_ratio REAL NOT NULL,
                occurrence_count INTEGER NOT NULL,
                participant_count INTEGER NOT NULL,
                salience REAL NOT NULL,
                first_period_date TEXT,
                last_period_date TEXT,
                source_message_ids_json TEXT NOT NULL
            );
            CREATE VIEW analysis_a4_topics AS SELECT * FROM topic_rows;
            """
        )
        for message_id in range(1, message_count + 1):
            conn.execute(
                """INSERT INTO analysis_messages
                   (id, conversation_id, sender_id, sent_at_utc_us, message_type, text)
                   VALUES (?, 7, ?, ?, 'text', ?)""",
                (
                    message_id,
                    11 if message_id % 2 else 22,
                    BASE_US + message_id * 60_000_000,
                    f"synthetic message {message_id}",
                ),
            )
        conn.execute(
            """INSERT INTO topic_rows (
                   conversation_id, topic_key, method, normalized_phrase, ngram_size,
                   document_frequency, document_frequency_ratio, occurrence_count,
                   participant_count, salience, first_period_date, last_period_date,
                   source_message_ids_json
               ) VALUES (7, 'synthetic-topic', 'lexical_ngram_v1', 'synthetic topic', 2,
                         ?, 0.5, ?, 2, 42.0, '2025-01-01', '2025-01-02', ?)""",
            (
                len(evidence_ids),
                len(evidence_ids),
                json.dumps(evidence_ids),
            ),
        )
    return database


def test_oversized_lexical_topic_is_losslessly_chunked_chronologically(tmp_path: Path):
    evidence_ids = list(range(250, 0, -1))
    database = _database(tmp_path, message_count=250, evidence_ids=evidence_ids)

    chunks = A4SQLiteCandidateSource(database).topics("7")

    assert LEXICAL_TOPIC_EVIDENCE_CHUNK_SIZE == 120
    assert [len(chunk.evidence_message_ids) for chunk in chunks] == [120, 120, 10]
    flattened = [message_id for chunk in chunks for message_id in chunk.evidence_message_ids]
    assert flattened == [str(message_id) for message_id in range(1, 251)]
    assert len(flattened) == len(set(flattened)) == 250

    for index, chunk in enumerate(chunks, start=1):
        assert chunk.candidate_type == "lexical_topic"
        assert chunk.metadata["parent_evidence_message_count"] == 250
        assert chunk.metadata["evidence_chunk_index"] == index
        assert chunk.metadata["evidence_chunk_count"] == 3
        assert chunk.metadata["evidence_chunk_size_limit"] == 120
        assert chunk.metadata["evidence_chunk_strategy"] == "chronological_partition_v1"
        assert chunk.metadata["candidate_semantics"] == "lexical_evidence_not_semantic_topic"
        assert chunk.id.endswith(f"chunk:{index:03d}-of-003")


def test_each_topic_chunk_stays_within_bounded_context(tmp_path: Path):
    evidence_ids = list(range(1, 251))
    database = _database(tmp_path, message_count=250, evidence_ids=evidence_ids)
    chunks = A4SQLiteCandidateSource(database).topics("7")
    builder = ContextBuilder(A2SQLiteMessageSource(database), max_messages=180)

    checked_ids: list[str] = []
    for chunk in chunks:
        request = AIAnalysisRequest(
            conversation_id="7",
            analysis_type=AnalysisType.LONGITUDINAL,
            start_ts=chunk.start_ts,
            end_ts=chunk.end_ts,
            mode=AnalysisMode.RETROSPECTIVE,
            candidate_id=chunk.id,
        )
        context = builder.build(request, chunk)
        assert len(context.messages) <= 180
        assert len(context.evidence_message_ids) == len(chunk.evidence_message_ids)
        assert not context.missing_evidence_message_ids
        assert not any("although max_messages=" in warning for warning in context.quality_warnings)
        checked_ids.extend(context.evidence_message_ids)

    assert checked_ids == [str(message_id) for message_id in range(1, 251)]


def test_topic_chunking_fails_closed_when_evidence_has_no_timestamped_message(tmp_path: Path):
    database = _database(
        tmp_path,
        message_count=120,
        evidence_ids=list(range(1, 121)) + [999],
    )

    with pytest.raises(A4SQLiteSourceError, match="unavailable from timestamped analysis_messages"):
        A4SQLiteCandidateSource(database).topics("7")
