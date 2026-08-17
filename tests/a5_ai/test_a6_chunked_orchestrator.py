from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from analyzazprav.a5_ai import (
    AnalysisMode,
    AnalysisStatus,
    AnalysisType,
    analyze_a6_packet_chunked,
    chunk_a6_packet,
)


BASE = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)


def _packet(count: int) -> dict[str, Any]:
    messages = []
    selected = []
    for index in range(count):
        message_id = f"m{index:03d}"
        selected.append(message_id)
        messages.append(
            {
                "membership_id": f"membership-{index:03d}",
                "message_id": message_id,
                "conversation_id": "conversation-test",
                "sender": "P1" if index % 2 == 0 else "P2",
                "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
                "text": f"PRIVATE-RAW-TEXT-{index:03d}",
                "selected": True,
            }
        )
    return {
        "schema_version": 1,
        "selected_message_ids": selected,
        "selected_message_count": count,
        "message_count": count,
        "context_before": 0,
        "context_after": 0,
        "messages": messages,
    }


def _valid_payload(message_ids: str | list[str], *, summary: str) -> dict[str, Any]:
    ids = [message_ids] if isinstance(message_ids, str) else list(message_ids)
    evidence = {"message_ids": ids, "description": "validated evidence"}
    return {
        "summary": {"text": summary, "confidence": 0.8, "evidence": evidence},
        "observations": [
            {"text": f"observation {summary}", "evidence": evidence, "strength": 0.8}
        ],
        "interpretations": [
            {
                "text": f"interpretation {summary}",
                "evidence_message_ids": ids,
                "confidence": 0.7,
            }
        ],
        "patterns": [],
        "turning_points": [],
        "participant_p1": None,
        "participant_p2": None,
        "shared_dynamic": None,
        "alternative_explanations": ["alternative"],
        "unknowns": ["unknown"],
        "overall_confidence": 0.75,
    }


class RecordingSequenceProvider:
    def __init__(self, payloads: list[Mapping[str, Any]]) -> None:
        self.payloads = [deepcopy(dict(item)) for item in payloads]
        self.calls: list[dict[str, str]] = []

    @property
    def provider_name(self) -> str:
        return "recording-sequence"

    @property
    def model_name(self) -> str:
        return "test-model"

    def analyze(self, *, system_prompt: str, user_prompt: str) -> Mapping[str, Any]:
        if len(self.calls) >= len(self.payloads):
            raise AssertionError("provider exhausted")
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return deepcopy(self.payloads[len(self.calls) - 1])


def test_chunk_a6_packet_preserves_all_selected_evidence_exactly_once() -> None:
    packet = _packet(250)

    chunks = chunk_a6_packet(packet, max_evidence_per_chunk=120)

    assert [len(chunk["selected_message_ids"]) for chunk in chunks] == [120, 120, 10]
    covered = [message_id for chunk in chunks for message_id in chunk["selected_message_ids"]]
    assert covered == packet["selected_message_ids"]
    assert len(set(covered)) == 250
    for chunk_index, chunk in enumerate(chunks, start=1):
        selected = set(chunk["selected_message_ids"])
        assert chunk["chunking"]["chunk_index"] == chunk_index
        assert chunk["chunking"]["chunk_count"] == 3
        assert chunk["chunking"]["parent_selected_message_count"] == 250
        assert all(
            bool(message["selected"]) == (message["message_id"] in selected)
            for message in chunk["messages"]
        )


def test_multi_chunk_analysis_synthesizes_without_raw_message_text() -> None:
    packet = _packet(250)
    provider = RecordingSequenceProvider(
        [
            _valid_payload("m000", summary="chunk one"),
            _valid_payload("m120", summary="chunk two"),
            _valid_payload("m240", summary="chunk three"),
            _valid_payload(["m000", "m120", "m240"], summary="final synthesis"),
        ]
    )

    execution = analyze_a6_packet_chunked(
        packet,
        provider=provider,
        analysis_type=AnalysisType.SEGMENT,
        mode=AnalysisMode.BLIND,
    )

    assert execution.status == AnalysisStatus.COMPLETED
    assert execution.result is not None
    assert execution.result.summary == "final synthesis"
    assert execution.chunk_count == 3
    assert execution.synthesis_used is True
    assert [item.evidence_count for item in execution.chunks] == [120, 120, 10]
    assert len(provider.calls) == 4

    synthesis_prompt = provider.calls[-1]["user"]
    assert "chunk one" in synthesis_prompt
    assert "chunk two" in synthesis_prompt
    assert "chunk three" in synthesis_prompt
    assert "PRIVATE-RAW-TEXT" not in synthesis_prompt
    assert "membership-" not in synthesis_prompt
    assert "source_record" not in synthesis_prompt
    assert '"m000"' in synthesis_prompt
    assert '"m120"' in synthesis_prompt
    assert '"m240"' in synthesis_prompt


def test_synthesis_cannot_cite_message_not_cited_by_validated_chunks() -> None:
    packet = _packet(121)
    invalid_synthesis = _valid_payload("m050", summary="invented synthesis evidence")
    provider = RecordingSequenceProvider(
        [
            _valid_payload("m000", summary="chunk one"),
            _valid_payload("m120", summary="chunk two"),
            invalid_synthesis,
            invalid_synthesis,
        ]
    )

    execution = analyze_a6_packet_chunked(
        packet,
        provider=provider,
        analysis_type=AnalysisType.SEGMENT,
        mode=AnalysisMode.BLIND,
    )

    assert execution.status == AnalysisStatus.FAILED_VALIDATION
    assert execution.result is None
    assert execution.synthesis_used is True
    assert execution.error is not None
    assert "outside supplied context" in execution.error
    assert len(provider.calls) == 4


def test_failed_chunk_stops_before_later_chunks_and_synthesis() -> None:
    packet = _packet(121)
    invalid = _valid_payload("outside-packet", summary="invalid")
    provider = RecordingSequenceProvider(
        [
            _valid_payload("m000", summary="chunk one"),
            invalid,
            invalid,
        ]
    )

    execution = analyze_a6_packet_chunked(
        packet,
        provider=provider,
        analysis_type=AnalysisType.SEGMENT,
        mode=AnalysisMode.BLIND,
    )

    assert execution.status == AnalysisStatus.FAILED_VALIDATION
    assert execution.result is None
    assert execution.chunk_count == 2
    assert len(execution.chunks) == 2
    assert execution.synthesis_used is False
    assert "chunk 2/2 failed" in str(execution.error)
    assert len(provider.calls) == 3
