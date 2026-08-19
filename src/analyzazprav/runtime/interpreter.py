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

PROMPT_VERSION = "runtime-v2-compact-1"
ALLOWED_KINDS = {"observation", "pattern", "interpretation", "uncertainty"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
MAX_CLAIMS = 8

SYSTEM_PROMPT = """You interpret a small evidence pack from a message conversation.
Return JSON only: {"summary":"...","claims":[{"kind":"observation|pattern|interpretation|uncertainty","text":"...","evidence":["E1"],"confidence":"low|medium|high"}]}.
Use only evidence labels present in the input. Every claim must cite at least one label. Separate direct observations from interpretations. Do not diagnose a person or state hidden motives as facts. Prefer uncertainty when evidence is limited. Keep the answer concise; maximum 8 claims."""


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

    raw_claims = result.get("claims")
    if not isinstance(raw_claims, list):
        raise RuntimeValidationError("provider result claims must be an array")
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
