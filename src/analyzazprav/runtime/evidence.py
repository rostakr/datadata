from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Mapping, Sequence

from .models import EvidenceItem, EvidencePack, RuntimeValidationError, require_mapping


class EvidenceBudgetExceeded(RuntimeValidationError):
    pass


def _text(value: Any, *, path: str) -> str:
    if value is None:
        raise RuntimeValidationError(f"{path} is required")
    result = str(value)
    if not result:
        raise RuntimeValidationError(f"{path} must not be empty")
    return result


def _tuple_of_strings(value: Any, *, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeValidationError(f"{path} must be an array")
    return tuple(sorted({str(item) for item in value if str(item)}))


def _timestamp(value: Any, *, path: str) -> str:
    text = _text(value, path=path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeValidationError(f"{path} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise RuntimeValidationError(f"{path} must include timezone information")
    return text


def _provider_size(items: Sequence[EvidenceItem], question: str | None) -> int:
    payload: dict[str, Any] = {
        "evidence": [item.provider_dict() for item in items],
    }
    if question:
        payload["question"] = question
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _with_labels(rows: Sequence[dict[str, Any]]) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            label=f"E{index}",
            message_id=row["message_id"],
            membership_id=row["membership_id"],
            conversation_id=row["conversation_id"],
            sender=row["sender"],
            timestamp=row["timestamp"],
            text=row["text"],
            source_record_keys=row["source_record_keys"],
            source_snapshot_keys=row["source_snapshot_keys"],
            source_parser_versions=row["source_parser_versions"],
        )
        for index, row in enumerate(rows, start=1)
    )


def _validate_packet(packet: Mapping[str, Any]) -> tuple[list[dict[str, Any]], set[str], str]:
    if packet.get("schema_version") != 1:
        raise RuntimeValidationError("Unsupported analysis packet schema_version")

    raw_messages = packet.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise RuntimeValidationError("analysis packet messages must be a non-empty array")

    raw_selected = packet.get("selected_message_ids")
    if not isinstance(raw_selected, list) or not raw_selected:
        raise RuntimeValidationError("analysis packet selected_message_ids must be a non-empty array")
    selected_ids = [str(value) for value in raw_selected]
    if len(selected_ids) != len(set(selected_ids)):
        raise RuntimeValidationError("selected_message_ids contains duplicates")
    selected_set = set(selected_ids)

    provenance_required = bool(packet.get("source_provenance_required"))
    if provenance_required and packet.get("source_provenance_status") != "complete":
        raise RuntimeValidationError("production packet source provenance is incomplete")

    rows: list[dict[str, Any]] = []
    seen_messages: set[str] = set()
    seen_memberships: set[str] = set()
    conversations: set[str] = set()

    for index, raw_value in enumerate(raw_messages):
        raw = require_mapping(raw_value, path=f"messages[{index}]")
        message_id = _text(raw.get("message_id"), path=f"messages[{index}].message_id")
        membership_id = _text(raw.get("membership_id"), path=f"messages[{index}].membership_id")
        conversation_id = _text(raw.get("conversation_id"), path=f"messages[{index}].conversation_id")
        sender = _text(raw.get("sender"), path=f"messages[{index}].sender")
        timestamp = _timestamp(raw.get("timestamp"), path=f"messages[{index}].timestamp")
        text = str(raw.get("text") or "")

        if message_id in seen_messages:
            raise RuntimeValidationError(f"duplicate message_id: {message_id}")
        if membership_id in seen_memberships:
            raise RuntimeValidationError(f"duplicate membership_id: {membership_id}")
        seen_messages.add(message_id)
        seen_memberships.add(membership_id)
        conversations.add(conversation_id)

        record_keys = _tuple_of_strings(
            raw.get("source_record_keys"), path=f"messages[{index}].source_record_keys"
        )
        snapshot_keys = _tuple_of_strings(
            raw.get("source_snapshot_keys"), path=f"messages[{index}].source_snapshot_keys"
        )
        parser_versions = _tuple_of_strings(
            raw.get("source_parser_versions"), path=f"messages[{index}].source_parser_versions"
        )
        if provenance_required:
            if raw.get("source_provenance_status") != "complete" or not record_keys or not snapshot_keys:
                raise RuntimeValidationError(
                    f"messages[{index}] lacks complete required source provenance"
                )

        rows.append(
            {
                "message_id": message_id,
                "membership_id": membership_id,
                "conversation_id": conversation_id,
                "sender": sender,
                "timestamp": timestamp,
                "text": text,
                "source_record_keys": record_keys,
                "source_snapshot_keys": snapshot_keys,
                "source_parser_versions": parser_versions,
                "selected": message_id in selected_set,
            }
        )

    if len(conversations) != 1:
        raise RuntimeValidationError("analysis packet spans multiple conversations")
    missing = selected_set - seen_messages
    if missing:
        raise RuntimeValidationError(
            "selected messages are missing from packet context: " + ", ".join(sorted(missing))
        )

    rows.sort(key=lambda row: (datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")), row["message_id"]))
    return rows, selected_set, next(iter(conversations))


def compile_packet_to_packs(
    packet: Mapping[str, Any],
    *,
    question: str | None = None,
    max_input_chars: int = 6000,
) -> tuple[EvidencePack, ...]:
    """Compile a validated A6-compatible packet into compact runtime-v2 packs.

    Selected messages are losslessly partitioned by actual serialized provider
    payload size. Non-selected context is added only when it fits. Canonical IDs
    and provenance stay in the local EvidenceItem map and are never serialized by
    ``EvidencePack.provider_payload()``.
    """

    if max_input_chars < 1000:
        raise RuntimeValidationError("max_input_chars must be at least 1000")
    clean_question = question.strip() if isinstance(question, str) and question.strip() else None
    rows, selected_set, conversation_id = _validate_packet(packet)
    selected_rows = [row for row in rows if row["message_id"] in selected_set]

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in selected_rows:
        candidate = current + [row]
        if _provider_size(_with_labels(candidate), clean_question) <= max_input_chars:
            current = candidate
            continue
        if not current:
            raise EvidenceBudgetExceeded(
                f"single selected message {row['message_id']} exceeds evidence budget"
            )
        groups.append(current)
        current = [row]
        if _provider_size(_with_labels(current), clean_question) > max_input_chars:
            raise EvidenceBudgetExceeded(
                f"single selected message {row['message_id']} exceeds evidence budget"
            )
    if current:
        groups.append(current)

    index_by_id = {row["message_id"]: index for index, row in enumerate(rows)}
    packs: list[EvidencePack] = []
    for group in groups:
        included = {row["message_id"] for row in group}
        selected_positions = [index_by_id[row["message_id"]] for row in group]
        context_candidates = [
            row for row in rows if row["message_id"] not in included
        ]
        context_candidates.sort(
            key=lambda row: (
                min(abs(index_by_id[row["message_id"]] - position) for position in selected_positions),
                index_by_id[row["message_id"]],
            )
        )

        expanded = list(group)
        for row in context_candidates:
            proposal = sorted(
                expanded + [row],
                key=lambda item: (
                    datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")),
                    item["message_id"],
                ),
            )
            if _provider_size(_with_labels(proposal), clean_question) <= max_input_chars:
                expanded = proposal

        items = _with_labels(expanded)
        if _provider_size(items, clean_question) > max_input_chars:
            raise AssertionError("evidence compiler exceeded its own provider budget")
        packs.append(
            EvidencePack(
                conversation_id=conversation_id,
                items=items,
                question=clean_question,
                max_input_chars=max_input_chars,
            )
        )

    return tuple(packs)
