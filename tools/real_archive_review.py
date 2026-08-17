from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class RealArchiveReviewError(RuntimeError):
    pass


_ALLOWED_UNSUPPORTED_REASONS: dict[str, set[str]] = {
    "chat_message_join": {
        "missing message_id or chat_id",
        "relation points to a missing message row",
    },
    "message_attachment_join": {
        "missing message_id or attachment_id",
        "relation points to a missing message row",
        "relation points to a missing attachment row",
    },
    "attachment": {
        "attachment row is referenced only by an unsupported relation",
        "attachment row is not referenced by message_attachment_join",
    },
}

_ALLOWED_A5_CANDIDATE_TYPES = {
    "conflict",
    "change_point",
    "engagement_signal",
    "dyadic_regime",
    "lexical_topic",
    "manual_selection",
}


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


def _read_optional_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_object(path)


def _issue_entries(report: Mapping[str, Any], severity: str) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    issues = report.get("issues") or []
    if not isinstance(issues, list):
        return result
    for issue in issues:
        if not isinstance(issue, Mapping):
            continue
        if str(issue.get("severity") or "").upper() == severity:
            result.append(issue)
    return result


def _issue_codes(report: Mapping[str, Any], severity: str) -> list[str]:
    return sorted(
        {
            str(issue.get("code") or "").strip()
            for issue in _issue_entries(report, severity)
            if str(issue.get("code") or "").strip()
        }
    )


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _unsupported_groups(reconciliation: Mapping[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    if reconciliation is None:
        return "UNAVAILABLE", []
    records = reconciliation.get("unsupported_records") or []
    if not isinstance(records, list):
        return "UNAVAILABLE", []

    groups: Counter[tuple[str, str]] = Counter()
    for record in records:
        if not isinstance(record, Mapping):
            groups[("OTHER", "OTHER")] += 1
            continue
        record_type = str(record.get("record_type") or "")
        reason = str(record.get("reason") or "")
        if record_type in _ALLOWED_UNSUPPORTED_REASONS and reason in _ALLOWED_UNSUPPORTED_REASONS[record_type]:
            groups[(record_type, reason)] += 1
        else:
            groups[("OTHER", "OTHER")] += 1

    return (
        "COMPLETE",
        [
            {"record_type": record_type, "reason": reason, "count": count}
            for (record_type, reason), count in sorted(groups.items())
        ],
    )


def _a5_category(detail: object) -> str:
    text = str(detail or "").casefold()
    if "unknown timestamp" in text:
        return "UNKNOWN_TIMESTAMPS"
    if "although max_messages=" in text:
        return "EVIDENCE_EXCEEDS_CONTEXT_LIMIT"
    if "legacy a2 fixture" in text:
        return "LEGACY_SOURCE_PROVENANCE"
    if "candidate evidence is unavailable" in text:
        return "MISSING_EVIDENCE"
    if "lack source_record_key provenance" in text:
        return "MISSING_SOURCE_PROVENANCE"
    return "OTHER"


def _a5_categories(report: Mapping[str, Any]) -> list[str]:
    categories = {
        _a5_category(issue.get("detail"))
        for severity in ("WARNING", "ERROR")
        for issue in _issue_entries(report, severity)
        if str(issue.get("code") or "").startswith("A5_")
    }
    return sorted(categories)


def _a5_candidate_counts(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    probe = report.get("a5_probe") or {}
    if not isinstance(probe, Mapping):
        return []
    checked = probe.get("checked") or []
    if not isinstance(checked, list):
        return []

    result: list[dict[str, Any]] = []
    for item in checked:
        if not isinstance(item, Mapping):
            continue
        candidate_type = str(item.get("candidate_type") or "")
        if candidate_type not in _ALLOWED_A5_CANDIDATE_TYPES:
            candidate_type = "OTHER"
        result.append(
            {
                "candidate_type": candidate_type,
                "context_message_count": _count(item.get("context_message_count")),
                "available_message_count": _count(item.get("available_message_count")),
                "omitted_message_count": _count(item.get("omitted_message_count")),
                "evidence_message_count": _count(item.get("evidence_message_count")),
            }
        )
    return result


def classify_review(report_path: str | Path) -> dict[str, Any]:
    """Classify a local real-archive gate result without exposing private identifiers or paths."""

    path = Path(report_path).expanduser().resolve()
    report = _read_object(path)
    staging = path.parent / "a1_staging"
    manifest = _read_object(staging / "manifest.json")
    reconciliation = _read_optional_object(staging / "reconciliation.json")

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
    a5_categories = _a5_categories(report)
    a5_candidate_counts = _a5_candidate_counts(report)
    unsupported_grouping_status, unsupported_groups = _unsupported_groups(reconciliation)

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
        "contract": "real-archive-review-v3",
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
                "grouping_status": unsupported_grouping_status,
                "groups": unsupported_groups,
            },
            "a5_quality": {
                "present": bool(a5_warning_codes),
                "warning_codes": a5_warning_codes,
                "categories": a5_categories,
                "candidate_counts": a5_candidate_counts,
            },
        },
        "recommended_actions": actions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.real_archive_review",
        description=(
            "Classify an existing local real_archive_report.json into privacy-safe NEEDS_REVIEW categories. "
            "The command never prints local paths, conversation IDs, contacts, message text, source identifiers, "
            "candidate IDs, or attachment names."
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
