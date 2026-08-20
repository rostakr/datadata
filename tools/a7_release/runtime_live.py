from __future__ import annotations

import argparse
import json
from typing import Any, Mapping

from analyzazprav.runtime import RuntimeValidationError, analyze_packet, compile_packet_to_packs
from tools.a7_release.common import finalize, issue, write_report


PRIVATE_MESSAGE_ID = "synthetic-private-message-id"
PRIVATE_MEMBERSHIP_ID = "synthetic-private-membership-id"
PRIVATE_SOURCE_RECORD = "synthetic-private-source-record"


def _packet() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "selected_message_ids": [PRIVATE_MESSAGE_ID],
        "source_provenance_required": True,
        "source_provenance_status": "complete",
        "messages": [
            {
                "message_id": PRIVATE_MESSAGE_ID,
                "membership_id": PRIVATE_MEMBERSHIP_ID,
                "conversation_id": "conversation-1",
                "sender": "P1",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "text": "Synthetic evidence text",
                "source_record_keys": [PRIVATE_SOURCE_RECORD],
                "source_snapshot_keys": ["synthetic-snapshot"],
                "source_parser_versions": ["synthetic-parser"],
                "source_provenance_status": "complete",
            }
        ],
    }


class StaticProvider:
    provider_name = "static"
    model_name = "runtime-v2-contract-fixture"

    def __init__(self, *, bad_label: bool = False) -> None:
        self.bad_label = bad_label
        self.calls: list[str] = []

    def analyze(self, *, system_prompt: str, user_prompt: str) -> Mapping[str, Any]:
        self.calls.append(user_prompt)
        return {
            "summary": "Synthetic summary",
            "claims": [
                {
                    "kind": "observation",
                    "text": "Synthetic claim",
                    "evidence": ["E999" if self.bad_label else "E1"],
                    "confidence": "medium",
                }
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--contract-sha", required=True)
    args = parser.parse_args()

    checks: dict[str, Any] = {}
    issues: list[dict[str, str]] = []
    packet = _packet()

    try:
        packs = compile_packet_to_packs(packet, max_input_chars=6000)
    except Exception as exc:
        issues.append(issue("ERROR", "RUNTIME_PACK_BUILD_FAILED", type(exc).__name__))
        packs = ()

    checks["pack_count"] = len(packs)
    if len(packs) != 1:
        issues.append(issue("ERROR", "RUNTIME_PACK_COUNT_INVALID", str(len(packs))))

    if packs:
        serialized = json.dumps(packs[0].provider_payload(), ensure_ascii=False, sort_keys=True)
        checks["provider_payload_uses_e_labels"] = '"E1"' in serialized
        checks["provider_payload_hides_message_id"] = PRIVATE_MESSAGE_ID not in serialized
        checks["provider_payload_hides_membership_id"] = PRIVATE_MEMBERSHIP_ID not in serialized
        checks["provider_payload_hides_source_record"] = PRIVATE_SOURCE_RECORD not in serialized
        for name in (
            "provider_payload_uses_e_labels",
            "provider_payload_hides_message_id",
            "provider_payload_hides_membership_id",
            "provider_payload_hides_source_record",
        ):
            if checks[name] is not True:
                issues.append(issue("ERROR", "RUNTIME_PROVIDER_DISCLOSURE_CONTRACT_FAILED", name))

    provider = StaticProvider()
    try:
        result = analyze_packet(packet, provider=provider, max_input_chars=6000)
    except Exception as exc:
        issues.append(issue("ERROR", "RUNTIME_INTERPRETER_FAILED", type(exc).__name__))
        result = {}

    checks["provider_call_count"] = len(provider.calls)
    checks["result_status"] = result.get("status") if isinstance(result, Mapping) else None
    claims = result.get("claims") if isinstance(result, Mapping) else None
    checks["claim_count"] = len(claims) if isinstance(claims, list) else 0
    materialized = claims[0].get("evidence") if isinstance(claims, list) and claims else None
    checks["canonical_evidence_materialized_after_inference"] = bool(
        isinstance(materialized, Mapping)
        and materialized.get("message_ids") == [PRIVATE_MESSAGE_ID]
    )
    if checks["provider_call_count"] != 1:
        issues.append(issue("ERROR", "RUNTIME_PROVIDER_CALL_COUNT_INVALID", str(checks["provider_call_count"])))
    if checks["result_status"] != "COMPLETED":
        issues.append(issue("ERROR", "RUNTIME_RESULT_NOT_COMPLETED", str(checks["result_status"])))
    if checks["canonical_evidence_materialized_after_inference"] is not True:
        issues.append(issue("ERROR", "RUNTIME_LOCAL_EVIDENCE_MATERIALIZATION_FAILED", "claim evidence"))

    bad = StaticProvider(bad_label=True)
    rejected = False
    try:
        analyze_packet(packet, provider=bad, max_input_chars=6000)
    except RuntimeValidationError:
        rejected = True
    checks["negative_unknown_label_rejected"] = rejected
    checks["negative_probe_call_count"] = len(bad.calls)
    if not rejected or len(bad.calls) != 1:
        issues.append(issue(
            "ERROR",
            "RUNTIME_NEGATIVE_LABEL_PROBE_FAILED",
            f"rejected={rejected}, calls={len(bad.calls)}",
        ))

    report = finalize("runtime", checks, issues, contract_sha=args.contract_sha)
    write_report(report, args.report)
    return 0 if report["verdict"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
