from __future__ import annotations

from typing import Any, Mapping

from .evidence import compile_packet_to_packs
from .interpreter import CompactProvider, interpret_pack
from .models import EvidenceItem, InterpretationResult

RUNTIME_SCHEMA = "runtime-v2-1"


def _confidence_number(value: str) -> float:
    return {"low": 0.35, "medium": 0.65, "high": 0.9}.get(value, 0.0)


def _evidence_ref(items: list[EvidenceItem]) -> dict[str, Any]:
    seen: set[str] = set()
    unique: list[EvidenceItem] = []
    for item in items:
        if item.message_id in seen:
            continue
        seen.add(item.message_id)
        unique.append(item)
    return {
        "message_ids": [item.message_id for item in unique],
        "messages": [item.materialized_dict() for item in unique],
    }


def analyze_packet(
    packet: Mapping[str, Any],
    *,
    provider: CompactProvider,
    question: str | None = None,
    max_input_chars: int = 6000,
) -> dict[str, Any]:
    packs = compile_packet_to_packs(
        packet,
        question=question,
        max_input_chars=max_input_chars,
    )
    results: list[InterpretationResult] = []
    for pack in packs:
        results.append(interpret_pack(pack, provider=provider))

    claims = [claim for result in results for claim in result.claims]
    summaries = [result.summary for result in results]
    selected = packet.get("selected_message_ids") or []
    return {
        "schema_version": RUNTIME_SCHEMA,
        "status": "COMPLETED",
        "provider": provider.provider_name,
        "model": provider.model_name,
        "selected_message_count": len(selected),
        "pack_count": len(packs),
        "parts": [result.to_dict() for result in results],
        "summary": summaries[0] if len(summaries) == 1 else "\n\n".join(
            f"Část {index}: {summary}" for index, summary in enumerate(summaries, start=1)
        ),
        "claims": [claim.to_dict() for claim in claims],
    }


def to_legacy_execution(runtime_result: Mapping[str, Any]) -> dict[str, Any]:
    """Temporary A6 renderer adapter; no old A5 orchestration is used."""

    raw_claims = runtime_result.get("claims") or []
    observations: list[dict[str, Any]] = []
    interpretations: list[dict[str, Any]] = []
    patterns: list[dict[str, Any]] = []
    unknowns: list[str] = []
    all_items: list[EvidenceItem] = []
    confidence_values: list[float] = []

    for raw in raw_claims:
        if not isinstance(raw, Mapping):
            continue
        confidence_text = str(raw.get("confidence") or "")
        confidence = _confidence_number(confidence_text)
        confidence_values.append(confidence)
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), Mapping) else {}
        messages_raw = evidence.get("messages") if isinstance(evidence, Mapping) else []
        materialized: list[EvidenceItem] = []
        if isinstance(messages_raw, list):
            for item in messages_raw:
                if not isinstance(item, Mapping):
                    continue
                evidence_item = EvidenceItem(
                    label=str(item.get("label") or ""),
                    message_id=str(item.get("message_id") or ""),
                    membership_id=str(item.get("membership_id") or ""),
                    conversation_id=str(item.get("conversation_id") or ""),
                    sender=str(item.get("sender") or ""),
                    timestamp=str(item.get("timestamp") or ""),
                    text=str(item.get("text") or ""),
                    source_record_keys=tuple(item.get("source_record_keys") or ()),
                    source_snapshot_keys=tuple(item.get("source_snapshot_keys") or ()),
                    source_parser_versions=tuple(item.get("source_parser_versions") or ()),
                )
                materialized.append(evidence_item)
                all_items.append(evidence_item)
        evidence_ref = _evidence_ref(materialized)
        kind = str(raw.get("kind") or "")
        text = str(raw.get("text") or "")
        if kind == "observation":
            observations.append({"text": text, "strength": confidence, "evidence": evidence_ref})
        elif kind == "pattern":
            patterns.append(
                {
                    "pattern_type": "runtime_v2_pattern",
                    "description": text,
                    "confidence": confidence,
                    "evidence": evidence_ref,
                }
            )
        elif kind == "interpretation":
            interpretations.append({"text": text, "confidence": confidence, "evidence": evidence_ref})
        elif kind == "uncertainty":
            interpretations.append(
                {
                    "text": "Nejistota: " + text,
                    "confidence": confidence,
                    "evidence": evidence_ref,
                }
            )
            unknowns.append(text)

    overall = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    return {
        "status": "completed",
        "runtime_schema": runtime_result.get("schema_version"),
        "pack_count": runtime_result.get("pack_count"),
        "result": {
            "summary": runtime_result.get("summary") or "",
            "summary_evidence": _evidence_ref(all_items),
            "overall_confidence": overall,
            "observations": observations,
            "interpretations": interpretations,
            "patterns": patterns,
            "alternative_explanations": [],
            "unknowns": unknowns,
        },
    }
