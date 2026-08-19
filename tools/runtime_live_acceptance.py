from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from a6.data import load_sqlite_messages
from a6.evidence import PASS, load_current_message_provenance, reconcile_a5_evidence_ref
from analyzazprav.a5_ai.providers import (
    OllamaProvider,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
)
from analyzazprav.runtime import RuntimeValidationError, analyze_packet, compile_packet_to_packs

SCHEMA_VERSION = "runtime-v2-live-acceptance-v1"


def _positive_float(value: str) -> float:
    result = float(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return result


def _positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return result


def _report(**updates: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": "ollama",
        "model": None,
        "selected_message_count": 0,
        "pack_count": 0,
        "claim_count": 0,
        "evidence_message_count": 0,
        "reconciliation": {"PASS": 0, "STALE": 0, "FAIL": 0, "UNVERIFIED": 0},
        "failure_reasons": [],
        "verdict": "FAIL",
    }
    base.update(updates)
    return base


def _load_packet(path: str | Path) -> Mapping[str, Any]:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise RuntimeValidationError("packet root must be an object")
    return raw


def run(args: argparse.Namespace) -> dict[str, Any]:
    model = args.model
    try:
        packet = _load_packet(args.packet)
        selected = packet.get("selected_message_ids")
        selected_count = len(selected) if isinstance(selected, list) else 0
        packs = compile_packet_to_packs(
            packet,
            question=args.question,
            max_input_chars=args.max_input_chars,
        )
    except (OSError, json.JSONDecodeError, RuntimeValidationError, ValueError):
        return _report(model=model, failure_reasons=["PACKET_INVALID"])

    provider = OllamaProvider(
        model,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        provider.preflight()
    except ProviderTimeout:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["PROVIDER_PREFLIGHT_TIMEOUT"],
        )
    except (ProviderUnavailable, ProviderError):
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["PROVIDER_UNAVAILABLE"],
        )

    try:
        result = analyze_packet(
            packet,
            provider=provider,
            question=args.question,
            max_input_chars=args.max_input_chars,
        )
    except ProviderTimeout:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["INFERENCE_TIMEOUT"],
        )
    except ProviderError:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["PROVIDER_ERROR"],
        )
    except RuntimeValidationError:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["MODEL_OUTPUT_INVALID"],
        )

    claims = result.get("claims") if isinstance(result, Mapping) else None
    if not isinstance(claims, list) or not claims:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            failure_reasons=["CLAIMS_MISSING"],
        )

    try:
        frame, _ = load_sqlite_messages(args.database)
    except Exception:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            claim_count=len(claims),
            failure_reasons=["CANONICAL_READ_FAILED"],
        )

    counts = {"PASS": 0, "STALE": 0, "FAIL": 0, "UNVERIFIED": 0}
    evidence_ids: set[str] = set()
    try:
        for claim in claims:
            if not isinstance(claim, Mapping):
                raise RuntimeValidationError("claim must be an object")
            evidence = claim.get("evidence")
            if not isinstance(evidence, Mapping):
                raise RuntimeValidationError("claim evidence missing")
            ids = [str(value) for value in evidence.get("message_ids") or []]
            evidence_ids.update(ids)
            current = frame[frame.message_id.astype(str).isin(ids)]
            current_rows = current[["membership_id", "message_id", "conversation_id"]].to_dict("records")
            sources = load_current_message_provenance(args.database, ids)
            reconciliation = reconcile_a5_evidence_ref(evidence, current_rows, sources)
            counts[reconciliation.status] = counts.get(reconciliation.status, 0) + 1
    except Exception:
        return _report(
            model=model,
            selected_message_count=selected_count,
            pack_count=len(packs),
            claim_count=len(claims),
            evidence_message_count=len(evidence_ids),
            reconciliation=counts,
            failure_reasons=["EVIDENCE_RECONCILIATION_FAILED"],
        )

    failure_reasons: list[str] = []
    if counts.get(PASS, 0) != len(claims):
        failure_reasons.append("EVIDENCE_RECONCILIATION_NOT_PASS")
    if not evidence_ids:
        failure_reasons.append("MESSAGE_EVIDENCE_MISSING")

    return _report(
        model=model,
        selected_message_count=selected_count,
        pack_count=len(packs),
        claim_count=len(claims),
        evidence_message_count=len(evidence_ids),
        reconciliation=counts,
        failure_reasons=failure_reasons,
        verdict="PASS" if not failure_reasons else "FAIL",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Runtime v2 local live acceptance")
    result.add_argument("--database", required=True)
    result.add_argument("--packet", required=True)
    result.add_argument("--model", default="qwen3:1.7b")
    result.add_argument("--base-url", default="http://localhost:11434")
    result.add_argument("--timeout-seconds", type=_positive_float, default=300.0)
    result.add_argument("--max-input-chars", type=_positive_int, default=6000)
    result.add_argument("--question", default=None)
    return result


def main() -> int:
    args = parser().parse_args()
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
