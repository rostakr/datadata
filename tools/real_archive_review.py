from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class RealArchiveReviewError(RuntimeError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RealArchiveReviewError(f"Required file not found: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise RealArchiveReviewError(f"Invalid JSON in {path.name}") from exc
    if not isinstance(value, dict):
        raise RealArchiveReviewError(f"Expected JSON object in {path.name}")
    return value


def _issue_codes(report: Mapping[str, Any], severity: str) -> list[str]:
    codes: set[str] = set()
    issues = report.get("issues") or []
    if not isinstance(issues, list):
        return []
    for issue in issues:
        if not isinstance(issue, Mapping):
            continue
        if str(issue.get("severity") or "").upper() != severity:
            continue
        code = str(issue.get("code") or "").strip()
        if code:
            codes.add(code)
    return sorted(codes)


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def classify_review(report_path: str | Path) -> dict[str, Any]:
    """Classify a local real-archive gate result without exposing private identifiers or paths."""

    path = Path(report_path).expanduser().resolve()
    report = _read_object(path)
    manifest = _read_object(path.parent / "a1_staging" / "manifest.json")

    manifest_counts = manifest.get("counts") or {}
    if not isinstance(manifest_counts, Mapping):
        manifest_counts = {}
    report_counts = report.get("a1_counts") or {}
    if not isinstance(report_counts, Mapping):
        report_counts = {}

    def count(name: str) -> int:
        if name in manifest_counts:
            return _count(manifest_counts.get(name))
        return _count(report_counts.get(name))

    attachments = manifest.get("attachments") or {}
    if not isinstance(attachments, Mapping):
        attachments = {}
    root_supplied = bool(attachments.get("root"))
    missing_attachments = count("attachments_missing")
    unsupported = count("unsupported")

    warning_codes = _issue_codes(report, "WARNING")
    error_codes = _issue_codes(report, "ERROR")
    a5_warning_codes = [code for code in warning_codes if code.startswith("A5_")]

    if missing_attachments == 0:
        attachment_state = "NONE"
    elif root_supplied:
        attachment_state = "UNRESOLVED_WITH_ROOT"
    else:
        attachment_state = "UNVERIFIED_NO_ROOT"

    actions: list[str] = []
    if attachment_state == "UNVERIFIED_NO_ROOT":
        actions.append("rerun_gate_with_attachments_root")
    elif attachment_state == "UNRESOLVED_WITH_ROOT":
        actions.append("inspect_unresolved_attachments_locally")
    if unsupported:
        actions.append("review_a1_unsupported_records_locally")
    if a5_warning_codes:
        actions.append("review_a5_quality_warnings_locally")
    if error_codes:
        actions.append("resolve_gate_errors_before_release")

    return {
        "contract": "real-archive-review-v1",
        "gate_status": str(report.get("status") or "UNKNOWN"),
        "gate_verdict": str(report.get("verdict") or "UNKNOWN"),
        "release_ready": bool(report.get("release_ready")),
        "warning_codes": warning_codes,
        "error_codes": error_codes,
        "review": {
            "attachments": {
                "state": attachment_state,
                "root_supplied": root_supplied,
                "missing_occurrence_count": missing_attachments,
            },
            "unsupported_records": {
                "present": unsupported > 0,
                "count": unsupported,
            },
            "a5_quality": {
                "present": bool(a5_warning_codes),
                "warning_codes": a5_warning_codes,
            },
        },
        "recommended_actions": actions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.real_archive_review",
        description=(
            "Classify an existing local real_archive_report.json into privacy-safe NEEDS_REVIEW categories. "
            "The command never prints local paths, conversation IDs, contacts, message text, or attachment names."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = classify_review(args.report)
    except RealArchiveReviewError as exc:
        print(json.dumps({"status": "FAIL", "code": "REVIEW_INPUT_INVALID", "detail": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
