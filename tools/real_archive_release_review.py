from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.real_archive_review import RealArchiveReviewError, classify_review


_NONBLOCKING_UNSUPPORTED = {
    (
        "attachment",
        "attachment row is not referenced by message_attachment_join",
    )
}


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _unsupported_release_policy(
    review: Mapping[str, Any],
) -> dict[str, Any]:
    unsupported = review.get("unsupported_records") or {}
    if not isinstance(unsupported, Mapping):
        unsupported = {}

    expected_count = _count(unsupported.get("count"))
    grouping_status = str(unsupported.get("grouping_status") or "UNAVAILABLE")
    raw_groups = unsupported.get("groups") or []
    groups = raw_groups if isinstance(raw_groups, list) else []

    grouped_count = 0
    nonblocking_count = 0
    blocking_count = 0
    classified_groups: list[dict[str, Any]] = []

    for group in groups:
        if not isinstance(group, Mapping):
            continue
        record_type = str(group.get("record_type") or "OTHER")
        reason = str(group.get("reason") or "OTHER")
        count = _count(group.get("count"))
        grouped_count += count
        nonblocking = (record_type, reason) in _NONBLOCKING_UNSUPPORTED
        if nonblocking:
            nonblocking_count += count
        else:
            blocking_count += count
        classified_groups.append(
            {
                "record_type": record_type,
                "reason": reason,
                "count": count,
                "release_blocking": not nonblocking,
            }
        )

    classification_complete = (
        grouping_status == "COMPLETE" and grouped_count == expected_count
    )
    unclassified_count = max(0, expected_count - grouped_count)
    if unclassified_count:
        blocking_count += unclassified_count
    if expected_count > 0 and not classification_complete and blocking_count == 0:
        # Fail closed even for impossible/over-counted groupings.
        blocking_count = 1

    return {
        "present": expected_count > 0,
        "count": expected_count,
        "grouping_status": grouping_status,
        "classification_complete": classification_complete,
        "grouped_count": grouped_count,
        "unclassified_count": unclassified_count,
        "nonblocking_count": nonblocking_count,
        "blocking_count": blocking_count,
        "groups": classified_groups,
    }


def evaluate_release_policy(report_path: str | Path) -> dict[str, Any]:
    """Apply a conservative release policy without changing the raw gate report.

    The only non-blocking A1 unsupported record is a standalone attachment row
    that has no message_attachment_join reference at all. Every broken relation,
    unknown reason, missing grouping, and count mismatch remains fail-closed.
    """

    base = classify_review(report_path)
    review = base.get("review") or {}
    if not isinstance(review, Mapping):
        review = {}

    unsupported_policy = _unsupported_release_policy(review)

    warning_codes = set(str(code) for code in (base.get("warning_codes") or []))
    error_codes = set(str(code) for code in (base.get("error_codes") or []))
    base_verdict = str(base.get("gate_verdict") or "UNKNOWN").upper()

    if unsupported_policy["present"]:
        if (
            unsupported_policy["classification_complete"]
            and unsupported_policy["blocking_count"] == 0
        ):
            warning_codes.discard("A1_UNSUPPORTED_RECORDS_PRESENT")
        else:
            warning_codes.add("A1_UNSUPPORTED_RECORDS_PRESENT")
            if not unsupported_policy["classification_complete"]:
                warning_codes.add("A1_UNSUPPORTED_CLASSIFICATION_INCOMPLETE")

    actions = [str(action) for action in (base.get("recommended_actions") or [])]
    if (
        unsupported_policy["classification_complete"]
        and unsupported_policy["blocking_count"] == 0
    ):
        actions = [
            action
            for action in actions
            if action != "review_a1_unsupported_records_locally"
        ]
    elif unsupported_policy["present"] and "review_a1_unsupported_records_locally" not in actions:
        actions.append("review_a1_unsupported_records_locally")

    if base_verdict == "INVALID" or error_codes:
        status = "FAIL"
        verdict = "INVALID"
    elif warning_codes:
        status = "WARNING"
        verdict = "NEEDS_REVIEW"
    else:
        status = "PASS"
        verdict = "VALID"

    return {
        "contract": "real-archive-release-review-v1",
        "base_gate_status": str(base.get("gate_status") or "UNKNOWN"),
        "base_gate_verdict": str(base.get("gate_verdict") or "UNKNOWN"),
        "base_release_ready": bool(base.get("release_ready")),
        "status": status,
        "verdict": verdict,
        "release_ready": verdict == "VALID",
        "warning_codes": sorted(warning_codes),
        "error_codes": sorted(error_codes),
        "review": {
            "attachments": dict(review.get("attachments") or {}),
            "unsupported_records": unsupported_policy,
            "a5_quality": dict(review.get("a5_quality") or {}),
        },
        "recommended_actions": actions,
        "policy_notes": [
            "raw_gate_report_unchanged",
            "unreferenced_attachment_rows_are_audit_only",
            "broken_or_unknown_unsupported_records_remain_release_blocking",
            "raw_invalid_verdict_can_never_be_promoted",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.real_archive_release_review",
        description=(
            "Evaluate a privacy-safe release verdict over an existing real-archive gate report. "
            "The raw report is never modified."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_release_policy(args.report)
    except RealArchiveReviewError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "verdict": "INVALID",
                    "code": "RELEASE_REVIEW_INPUT_INVALID",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
