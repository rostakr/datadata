from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.real_archive_attachment_review import (
    AttachmentReviewError,
    audit_attachment_resolution,
)
from tools.real_archive_review import RealArchiveReviewError, classify_review


_NONBLOCKING_UNSUPPORTED = {
    (
        "attachment",
        "attachment row is not referenced by message_attachment_join",
    )
}

_MEDIA_LIMITATION = "REFERENCED_ATTACHMENT_BINARIES_UNAVAILABLE"


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


def _attachment_release_policy(
    report_path: str | Path,
    review: Mapping[str, Any],
    *,
    attachments_root: str | Path | None = None,
) -> dict[str, Any]:
    attachments = review.get("attachments") or {}
    if not isinstance(attachments, Mapping):
        attachments = {}

    expected_missing = _count(attachments.get("missing_occurrence_count"))
    if expected_missing == 0:
        return {
            "present": False,
            "audited": False,
            "classification_complete": True,
            "release_blocking": False,
            "missing_occurrence_count": 0,
            "not_found_count": 0,
            "exact_normalization_recoverable_count": 0,
            "relocated_unique_candidate_count": 0,
            "ambiguous_candidate_count": 0,
            "physical_absence_likely": False,
            "resolver_fix_indicated": False,
            "relocation_investigation_indicated": False,
        }

    try:
        audit = audit_attachment_resolution(
            report_path,
            attachments_root=attachments_root,
        )
    except AttachmentReviewError:
        return {
            "present": True,
            "audited": False,
            "classification_complete": False,
            "release_blocking": True,
            "missing_occurrence_count": expected_missing,
            "not_found_count": 0,
            "exact_normalization_recoverable_count": 0,
            "relocated_unique_candidate_count": 0,
            "ambiguous_candidate_count": 0,
            "physical_absence_likely": False,
            "resolver_fix_indicated": False,
            "relocation_investigation_indicated": False,
        }

    summary = audit.get("summary") or {}
    if not isinstance(summary, Mapping):
        summary = {}

    audited_missing = _count(audit.get("missing_occurrence_count"))
    exact_recoverable = _count(summary.get("exact_normalization_recoverable_count"))
    relocated_unique = _count(summary.get("relocated_unique_candidate_count"))
    ambiguous = _count(summary.get("ambiguous_candidate_count"))
    not_found = _count(summary.get("not_found_count"))
    resolver_fix = bool(summary.get("resolver_fix_indicated"))
    relocation_investigation = bool(summary.get("relocation_investigation_indicated"))
    physical_absence = bool(summary.get("physical_absence_likely"))

    classification_complete = (
        str(audit.get("status") or "") == "PASS"
        and expected_missing > 0
        and audited_missing == expected_missing
        and exact_recoverable == 0
        and relocated_unique == 0
        and ambiguous == 0
        and not_found == expected_missing
        and not resolver_fix
        and not relocation_investigation
        and physical_absence
    )

    return {
        "present": True,
        "audited": True,
        "classification_complete": classification_complete,
        "release_blocking": not classification_complete,
        "missing_occurrence_count": expected_missing,
        "not_found_count": not_found,
        "exact_normalization_recoverable_count": exact_recoverable,
        "relocated_unique_candidate_count": relocated_unique,
        "ambiguous_candidate_count": ambiguous,
        "physical_absence_likely": physical_absence,
        "resolver_fix_indicated": resolver_fix,
        "relocation_investigation_indicated": relocation_investigation,
    }


def evaluate_release_policy(
    report_path: str | Path,
    *,
    attachments_root: str | Path | None = None,
) -> dict[str, Any]:
    """Apply a conservative analysis-release policy without changing the raw gate report.

    Two narrow conditions may be non-blocking in this policy layer:

    1. a standalone attachment row that has no message_attachment_join relation;
    2. a referenced attachment binary that a privacy-safe local audit proves is
       physically unavailable, with no resolver, relocation or ambiguity signal.

    The second condition changes only canonical/text analysis readiness. It never
    claims media completeness and never modifies the raw NEEDS_REVIEW verdict.
    """

    base = classify_review(report_path)
    review = base.get("review") or {}
    if not isinstance(review, Mapping):
        review = {}

    unsupported_policy = _unsupported_release_policy(review)
    attachment_policy = _attachment_release_policy(
        report_path,
        review,
        attachments_root=attachments_root,
    )

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

    limitations: list[str] = []
    if attachment_policy["present"]:
        if (
            attachment_policy["classification_complete"]
            and not attachment_policy["release_blocking"]
        ):
            warning_codes.discard("A1_ATTACHMENTS_MISSING")
            limitations.append(_MEDIA_LIMITATION)
        else:
            warning_codes.add("A1_ATTACHMENTS_MISSING")

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

    if (
        attachment_policy["present"]
        and attachment_policy["classification_complete"]
        and not attachment_policy["release_blocking"]
    ):
        actions = [
            action
            for action in actions
            if action != "inspect_unresolved_attachments_locally"
        ]

    if base_verdict == "INVALID" or error_codes:
        status = "FAIL"
        verdict = "INVALID"
    elif warning_codes:
        status = "WARNING"
        verdict = "NEEDS_REVIEW"
    else:
        status = "PASS"
        verdict = "VALID"

    if attachment_policy["present"]:
        media_state = (
            "PARTIAL"
            if attachment_policy["classification_complete"]
            and not attachment_policy["release_blocking"]
            else "UNRESOLVED"
        )
    else:
        media_state = "COMPLETE"

    return {
        "contract": "real-archive-release-review-v2",
        "analysis_scope": "CANONICAL_TEXT_AND_METADATA",
        "base_gate_status": str(base.get("gate_status") or "UNKNOWN"),
        "base_gate_verdict": str(base.get("gate_verdict") or "UNKNOWN"),
        "base_release_ready": bool(base.get("release_ready")),
        "status": status,
        "verdict": verdict,
        "release_ready": verdict == "VALID",
        "warning_codes": sorted(warning_codes),
        "error_codes": sorted(error_codes),
        "limitations": limitations,
        "media_completeness": {
            "state": media_state,
            "referenced_binary_files_complete": not attachment_policy["present"],
            "missing_occurrence_count": attachment_policy["missing_occurrence_count"],
        },
        "review": {
            "attachments": dict(review.get("attachments") or {}),
            "attachment_absence": attachment_policy,
            "unsupported_records": unsupported_policy,
            "a5_quality": dict(review.get("a5_quality") or {}),
        },
        "recommended_actions": actions,
        "policy_notes": [
            "raw_gate_report_unchanged",
            "analysis_release_does_not_claim_media_completeness",
            "unreferenced_attachment_rows_are_audit_only",
            "proven_unavailable_referenced_attachment_binaries_are_an_explicit_media_limitation",
            "resolver_relocation_or_ambiguity_signals_remain_release_blocking",
            "broken_or_unknown_unsupported_records_remain_release_blocking",
            "raw_invalid_verdict_can_never_be_promoted",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.real_archive_release_review",
        description=(
            "Evaluate a privacy-safe canonical/text analysis release verdict over an existing "
            "real-archive gate report. The raw report is never modified."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--attachments-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_release_policy(
            args.report,
            attachments_root=args.attachments_root,
        )
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
