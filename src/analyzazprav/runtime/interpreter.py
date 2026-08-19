from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from .models import (
    Claim,
    EvidencePack,
    InterpretationResult,
    MaterializedClaim,
    RuntimeValidationError,
    require_mapping,
)

PROMPT_VERSION = "runtime-v2-compact-2"
ALLOWED_KINDS = {"observation", "pattern", "interpretation", "uncertainty"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
MAX_CLAIMS = 8

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 800},
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_CLAIMS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["observation", "pattern", "interpretation", "uncertainty"],
                    },
                    "text": {"type": "string", "minLength": 1, "maxLength": 500},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "uniqueItems": True,
                        "items": {"type": "string", "pattern": "^E[1-9][0-9]*$"},
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["kind", "text", "evidence", "confidence"],
            },
        },
    },
    "required": ["summary", "claims"],
}

SYSTEM_PROMPT = """Interpret the supplied message evidence. Return only the requested JSON structure. Use only E-labels present in the input and cite evidence for every claim. Separate observation from interpretation, do not diagnose people or state hidden motives as facts, and use uncertainty when evidence is limited. Be concise."""


class CompactProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def analyze(self, *, system_prompt: str, user_prompt: str) -> Mapping[str, Any]: ...


def build_user_prompt(pack: EvidencePack) -> str:
    return json.dumps(pack.provider_payload(), ensure_ascii=False, separators=(",", ":"))


def _parse_claim(value: Any, *, index: int, allowed_labels: set[str]) -> Claim:
    raw = require_mapping(value, path=f"claims[{index}]")
    kind = str(raw.get("kind") or "").strip()
    text = str(raw.get("text") or "").strip()
    confidence = str(raw.get("confidence") or "").strip()
    evidence_raw = raw.get("evidence")

    if kind not in ALLOWED_KINDS:
        raise RuntimeValidationError(f"claims[{index}].kind is invalid")
    if not text:
        raise RuntimeValidationError(f"claims[{index}].text is empty")
    if len(text) > 500:
        raise RuntimeValidationError(f"claims[{index}].text is too long")
    if confidence not in ALLOWED_CONFIDENCE:
        raise RuntimeValidationError(f"claims[{index}].confidence is invalid")
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise RuntimeValidationError(f"claims[{index}].evidence must be a non-empty array")

    labels = tuple(str(value).strip() for value in evidence_raw)
    if any(not label for label in labels):
        raise RuntimeValidationError(f"claims[{index}].evidence contains an empty label")
    if len(labels) != len(set(labels)):
        raise RuntimeValidationError(f"claims[{index}].evidence contains duplicate labels")
    unknown = set(labels) - allowed_labels
    if unknown:
        raise RuntimeValidationError(
            f"claims[{index}].evidence contains unknown labels: {sorted(unknown)!r}"
        )
    return Claim(kind=kind, text=text, evidence_labels=labels, confidence=confidence)


def interpret_pack(pack: EvidencePack, *, provider: CompactProvider) -> InterpretationResult:
    """Run exactly one compact inference and materialize evidence locally.

    No repair pass is attempted. An invalid model response fails immediately so
    latency and state transitions stay predictable.
    """

    raw = provider.analyze(system_prompt=SYSTEM_PROMPT, user_prompt=build_user_prompt(pack))
    result = require_mapping(raw, path="provider result")
    summary = str(result.get("summary") or "").strip()
    if not summary:
        raise RuntimeValidationError("provider result summary is empty")
    if len(summary) > 800:
        raise RuntimeValidationError("provider result summary is too long")

    raw_claims = result.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise RuntimeValidationError("provider result claims must be a non-empty array")
    if len(raw_claims) > MAX_CLAIMS:
        raise RuntimeValidationError(f"provider result exceeds {MAX_CLAIMS} claims")

    label_map = pack.label_map()
    allowed_labels = set(label_map)
    claims = tuple(
        _parse_claim(value, index=index, allowed_labels=allowed_labels)
        for index, value in enumerate(raw_claims)
    )
    materialized = tuple(
        MaterializedClaim(
            kind=claim.kind,
            text=claim.text,
            confidence=claim.confidence,
            evidence_labels=claim.evidence_labels,
            messages=tuple(label_map[label] for label in claim.evidence_labels),
        )
        for claim in claims
    )
    return InterpretationResult(
        summary=summary,
        claims=materialized,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=PROMPT_VERSION,
    )
