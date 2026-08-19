from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


class RuntimeValidationError(ValueError):
    """Raised when runtime-v2 input or model output violates the contract."""


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    message_id: str
    membership_id: str
    conversation_id: str
    sender: str
    timestamp: str
    text: str
    source_record_keys: tuple[str, ...] = ()
    source_snapshot_keys: tuple[str, ...] = ()
    source_parser_versions: tuple[str, ...] = ()

    def provider_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "text": self.text,
        }

    def materialized_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidencePack:
    conversation_id: str
    items: tuple[EvidenceItem, ...]
    question: str | None = None
    max_input_chars: int = 8000

    def label_map(self) -> dict[str, EvidenceItem]:
        return {item.label: item for item in self.items}

    def provider_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence": [item.provider_dict() for item in self.items],
        }
        if self.question:
            payload["question"] = self.question
        return payload


@dataclass(frozen=True)
class Claim:
    kind: str
    text: str
    evidence_labels: tuple[str, ...]
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "evidence": list(self.evidence_labels),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class MaterializedClaim:
    kind: str
    text: str
    confidence: str
    evidence_labels: tuple[str, ...]
    messages: tuple[EvidenceItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "confidence": self.confidence,
            "evidence_labels": list(self.evidence_labels),
            "evidence": {
                "message_ids": [item.message_id for item in self.messages],
                "messages": [item.materialized_dict() for item in self.messages],
            },
        }


@dataclass(frozen=True)
class InterpretationResult:
    summary: str
    claims: tuple[MaterializedClaim, ...]
    provider: str
    model: str
    prompt_version: str
    status: str = "COMPLETED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


def require_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeValidationError(f"{path} must be an object")
    return value
