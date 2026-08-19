from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from a6.evidence import (
    FAIL,
    PASS,
    STALE,
    UNVERIFIED,
    PacketProvenanceError,
    load_current_message_provenance,
    reconcile_a5_evidence_ref,
)


REPORT_SCHEMA_VERSION = "a5-live-acceptance-v1"


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _evidence_refs(result: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if result is None:
        return []

    refs: list[Mapping[str, Any]] = []

    def add(value: Any) -> None:
        ref = _mapping(value)
        if ref is not None:
            refs.append(ref)

    add(result.get("summary_evidence"))
    add(result.get("participant_p1_evidence"))
    add(result.get("participant_p2_evidence"))
    add(result.get("shared_dynamic_evidence"))

    for item in result.get("observations") or []:
        row = _mapping(item)
        if row is not None:
            add(row.get("evidence"))
    for item in result.get("interpretations") or []:
        row = _mapping(item)
        if row is not None:
            add(row.get("evidence"))
    for item in result.get("patterns") or []:
        row = _mapping(item)
        if row is not None:
            add(row.get("evidence"))
    for item in result.get("turning_point_evidence") or []:
        add(item)

    return refs


def _packet_message_rows(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_messages = packet.get("messages")
    if not isinstance(raw_messages, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw_messages:
        row = _mapping(item)
        if row is None:
            continue
        rows.append(
            {
                "message_id": row.get("message_id"),
                "membership_id": row.get("membership_id"),
                "conversation_id": row.get("conversation_id"),
            }
        )
    return rows


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_live_acceptance_report(
    execution: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    database: str | Path,
    model_name: str,
) -> dict[str, Any]:
    """Return a privacy-safe verdict for one fresh local A5 execution.

    The report deliberately contains no message/conversation/membership/source
    identifiers, message text, local paths, context hashes or model output.
    Evidence is reconciled against the current A2 source provenance, but only
    aggregate counts and allowlisted status categories leave this function.
    """

    execution_status = str(execution.get("status") or "unknown")
    result = _mapping(execution.get("result"))
    chunking = _mapping(execution.get("chunking")) or {}
    chunks = chunking.get("chunks") if isinstance(chunking.get("chunks"), list) else []

    chunk_count = _safe_int(chunking.get("chunk_count"))
    selected_message_count = _safe_int(chunking.get("selected_message_count"))
    completed_chunk_count = sum(
        1
        for item in chunks
        if isinstance(item, Mapping) and str(item.get("status") or "") == "completed"
    )

    refs = _evidence_refs(result)
    message_refs = [
        ref
        for ref in refs
        if isinstance(ref.get("message_ids"), (list, tuple)) and len(ref.get("message_ids") or []) > 0
    ]
    unique_ids = sorted(
        {
            str(message_id)
            for ref in message_refs
            for message_id in ref.get("message_ids") or []
            if message_id is not None
        }
    )
    message_reference_count = sum(len(ref.get("message_ids") or []) for ref in message_refs)

    reconciliation_counts: Counter[str] = Counter()
    provenance_lookup_failed = False
    if message_refs:
        try:
            current_sources = load_current_message_provenance(database, unique_ids)
            current_rows = _packet_message_rows(packet)
            for ref in message_refs:
                reconciliation = reconcile_a5_evidence_ref(ref, current_rows, current_sources)
                reconciliation_counts[reconciliation.status] += 1
        except PacketProvenanceError:
            provenance_lookup_failed = True

    failure_reasons: list[str] = []
    if execution_status != "completed":
        failure_reasons.append("EXECUTION_NOT_COMPLETED")
    if result is None:
        failure_reasons.append("RESULT_MISSING")
    if chunk_count < 1:
        failure_reasons.append("CHUNK_SUMMARY_MISSING")
    elif completed_chunk_count != chunk_count:
        failure_reasons.append("CHUNK_NOT_COMPLETED")
    if not message_refs:
        failure_reasons.append("MESSAGE_EVIDENCE_MISSING")
    if provenance_lookup_failed:
        failure_reasons.append("PROVENANCE_LOOKUP_FAILED")
    elif message_refs and reconciliation_counts[PASS] != len(message_refs):
        failure_reasons.append("EVIDENCE_RECONCILIATION_NOT_PASS")

    verdict = "PASS" if not failure_reasons else "FAIL"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "verdict": verdict,
        "provider": "ollama",
        "model": str(model_name),
        "fresh_inference_required": True,
        "execution_status": execution_status,
        "selected_message_count": selected_message_count,
        "chunk_count": chunk_count,
        "completed_chunk_count": completed_chunk_count,
        "synthesis_used": bool(chunking.get("synthesis_used")),
        "evidence_ref_count": len(refs),
        "message_evidence_ref_count": len(message_refs),
        "message_reference_count": message_reference_count,
        "unique_evidence_message_count": len(unique_ids),
        "reconciliation": {
            PASS: int(reconciliation_counts[PASS]),
            STALE: int(reconciliation_counts[STALE]),
            FAIL: int(reconciliation_counts[FAIL]),
            UNVERIFIED: int(reconciliation_counts[UNVERIFIED]),
        },
        "failure_reasons": failure_reasons,
    }


def failed_live_acceptance_report(*, model_name: str, reason: str) -> dict[str, Any]:
    """Create a privacy-safe fail-closed report for pre-verdict failures."""

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "verdict": "FAIL",
        "provider": "ollama",
        "model": str(model_name),
        "fresh_inference_required": True,
        "execution_status": "failed",
        "selected_message_count": 0,
        "chunk_count": 0,
        "completed_chunk_count": 0,
        "synthesis_used": False,
        "evidence_ref_count": 0,
        "message_evidence_ref_count": 0,
        "message_reference_count": 0,
        "unique_evidence_message_count": 0,
        "reconciliation": {PASS: 0, STALE: 0, FAIL: 0, UNVERIFIED: 0},
        "failure_reasons": [str(reason)],
    }
