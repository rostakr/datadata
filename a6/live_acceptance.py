from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
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


def _load_current_message_rows(
    database: str | Path,
    message_ids: list[str],
) -> list[dict[str, str]]:
    """Read current canonical membership identity directly from A2, read-only."""

    if not message_ids:
        return []
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise PacketProvenanceError("A2 database does not exist")

    placeholders = ",".join("?" for _ in message_ids)
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        objects = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        }
        if "analysis_messages" not in objects:
            raise PacketProvenanceError("A2 analysis_messages view is missing")
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(analysis_messages)").fetchall()
        }
        required = {"membership_id", "id", "conversation_id"}
        if not required.issubset(columns):
            raise PacketProvenanceError("A2 analysis_messages membership contract is incomplete")
        rows = conn.execute(
            f"""
            SELECT
                CAST(membership_id AS TEXT) AS membership_id,
                CAST(id AS TEXT) AS message_id,
                CAST(conversation_id AS TEXT) AS conversation_id
            FROM analysis_messages
            WHERE CAST(id AS TEXT) IN ({placeholders})
            ORDER BY CAST(id AS TEXT), CAST(conversation_id AS TEXT), CAST(membership_id AS TEXT)
            """,
            message_ids,
        ).fetchall()
    except PacketProvenanceError:
        raise
    except sqlite3.Error as exc:
        raise PacketProvenanceError("A2 current membership query failed") from exc
    finally:
        if "conn" in locals():
            conn.close()

    return [
        {
            "membership_id": str(row["membership_id"]),
            "message_id": str(row["message_id"]),
            "conversation_id": str(row["conversation_id"]),
        }
        for row in rows
    ]


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
    Evidence is reconciled against current A2 membership and source provenance,
    while only aggregate counts and allowlisted status categories leave this
    function. ``packet`` is retained in the API because it is the exact input
    whose execution is being accepted; current identity is never trusted from
    the packet itself.
    """

    del packet  # Never use a possibly stale packet as the current A2 identity oracle.

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
            current_rows = _load_current_message_rows(database, unique_ids)
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
