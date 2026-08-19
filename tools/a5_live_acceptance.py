from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from a6.a5_bridge import run_local_a5
from a6.evidence import PacketProvenanceError, enrich_analysis_packet_source_provenance
from a6.live_acceptance import build_live_acceptance_report, failed_live_acceptance_report


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one fresh local Ollama A5 inference from an A6 packet and emit only a "
            "privacy-safe acceptance verdict."
        )
    )
    parser.add_argument("--database", required=True, help="Local canonical messages.sqlite path")
    parser.add_argument("--packet", required=True, help="Local A6 a5-context.json path")
    parser.add_argument("--model", required=True, help="Exactly installed local Ollama model name")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Local Ollama base URL")
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_float,
        default=120.0,
        help="Timeout for each local Ollama /api/chat inference request (default: 120)",
    )
    parser.add_argument(
        "--analysis-type",
        default="segment",
        choices=(
            "segment",
            "change_point",
            "conflict",
            "interaction_cycle",
            "longitudinal",
            "relationship_dynamics",
            "psychological_hypotheses",
        ),
    )
    parser.add_argument("--mode", default="blind", choices=("blind", "retrospective"))
    return parser


def _emit(report: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(dict(report), ensure_ascii=False, sort_keys=True) + "\n")


def _load_packet(path: str | Path) -> Mapping[str, Any]:
    packet_path = Path(path).expanduser().resolve()
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("A6 packet root must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if os.environ.get("CODESPACES"):
        _emit(failed_live_acceptance_report(model_name=args.model, reason="LOCAL_ONLY_REQUIRED"))
        return 2

    try:
        packet = _load_packet(args.packet)
    except (OSError, ValueError, json.JSONDecodeError):
        _emit(failed_live_acceptance_report(model_name=args.model, reason="PACKET_LOAD_FAILED"))
        return 2

    try:
        packet = enrich_analysis_packet_source_provenance(
            packet,
            args.database,
            require_provenance=True,
        )
    except PacketProvenanceError:
        _emit(
            failed_live_acceptance_report(
                model_name=args.model,
                reason="PACKET_PROVENANCE_INVALID",
            )
        )
        return 1

    try:
        execution = run_local_a5(
            packet,
            model_name=args.model,
            base_url=args.base_url,
            analysis_type=args.analysis_type,
            mode=args.mode,
            force_refresh=True,
            inference_timeout_seconds=args.timeout_seconds,
        )
    except Exception:
        # Do not echo provider/model exceptions here: they can contain local paths,
        # message IDs or other private runtime context. The category is actionable
        # and the detailed exception remains local to an interactive debug run.
        _emit(
            failed_live_acceptance_report(
                model_name=args.model,
                reason="LIVE_EXECUTION_FAILED",
            )
        )
        return 1

    try:
        report = build_live_acceptance_report(
            execution,
            packet,
            database=args.database,
            model_name=args.model,
        )
    except Exception:
        _emit(
            failed_live_acceptance_report(
                model_name=args.model,
                reason="ACCEPTANCE_RECONCILIATION_FAILED",
            )
        )
        return 1

    _emit(report)
    return 0 if report.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
