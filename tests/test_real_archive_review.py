from __future__ import annotations

import json
from pathlib import Path

from tools.real_archive_review import classify_review


def _write_case(
    root: Path,
    *,
    attachment_root: str | None,
    missing: int,
    unsupported: int = 0,
    issues: list[dict[str, str]] | None = None,
    unsupported_records: list[dict[str, object]] | None = None,
    a5_checked: list[dict[str, object]] | None = None,
) -> Path:
    staging = root / "a1_staging"
    staging.mkdir(parents=True)
    (staging / "manifest.json").write_text(
        json.dumps(
            {
                "attachments": {"root": attachment_root},
                "counts": {
                    "attachments_missing": missing,
                    "unsupported": unsupported,
                },
            }
        ),
        encoding="utf-8",
    )
    (staging / "reconciliation.json").write_text(
        json.dumps({"unsupported_records": unsupported_records or []}),
        encoding="utf-8",
    )
    report = root / "real_archive_report.json"
    report.write_text(
        json.dumps(
            {
                "status": "WARNING",
                "verdict": "NEEDS_REVIEW",
                "release_ready": False,
                "issues": issues or [],
                "selector": {"conversation_id": 999},
                "source": {"path": "/private/example/chat.db"},
                "a5_probe": {"checked": a5_checked or []},
            }
        ),
        encoding="utf-8",
    )
    return report


def test_missing_attachments_without_root_are_unverified(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=3,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_ATTACHMENTS_MISSING",
                "detail": "synthetic",
            }
        ],
    )

    result = classify_review(report)

    assert result["contract"] == "real-archive-review-v3"
    assert result["gate_verdict"] == "NEEDS_REVIEW"
    assert result["release_ready"] is False
    assert result["review"]["attachments"] == {
        "state": "UNVERIFIED_NO_ROOT",
        "root_supplied": False,
        "missing_occurrence_count": 3,
    }
    assert result["recommended_actions"] == ["rerun_gate_with_attachments_root"]


def test_missing_attachments_with_root_are_truly_unresolved(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root="/private/example/Attachments",
        missing=2,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_ATTACHMENTS_MISSING",
                "detail": "synthetic",
            }
        ],
    )

    result = classify_review(report)

    assert result["review"]["attachments"]["state"] == "UNRESOLVED_WITH_ROOT"
    assert result["review"]["attachments"]["root_supplied"] is True
    assert result["recommended_actions"] == ["inspect_unresolved_attachments_locally"]


def test_review_summary_groups_known_unsupported_and_redacts_identifiers(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=0,
        unsupported=4,
        unsupported_records=[
            {
                "record_type": "attachment",
                "source_identifier": "PRIVATE-ATTACHMENT-ID-1",
                "reason": "attachment row is not referenced by message_attachment_join",
            },
            {
                "record_type": "attachment",
                "source_identifier": "PRIVATE-ATTACHMENT-ID-2",
                "reason": "attachment row is not referenced by message_attachment_join",
            },
            {
                "record_type": "message_attachment_join",
                "source_identifier": "PRIVATE-JOIN-ID",
                "message_id": "PRIVATE-MESSAGE-ID",
                "reason": "relation points to a missing attachment row",
            },
            {
                "record_type": "future_private_type",
                "source_identifier": "/private/example/secret",
                "reason": "future reason with private payload 999",
            },
        ],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            },
            {
                "severity": "WARNING",
                "code": "A5_CONTEXT_QUALITY_WARNING",
                "detail": "12 conversation membership(s) have unknown timestamp and cannot be placed in A5 temporal context without guessing.",
            },
        ],
    )

    result = classify_review(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["review"]["attachments"]["state"] == "NONE"
    assert result["review"]["unsupported_records"] == {
        "present": True,
        "count": 4,
        "grouping_status": "COMPLETE",
        "groups": [
            {
                "record_type": "OTHER",
                "reason": "OTHER",
                "count": 1,
            },
            {
                "record_type": "attachment",
                "reason": "attachment row is not referenced by message_attachment_join",
                "count": 2,
            },
            {
                "record_type": "message_attachment_join",
                "reason": "relation points to a missing attachment row",
                "count": 1,
            },
        ],
    }
    assert result["review"]["a5_quality"] == {
        "present": True,
        "warning_codes": ["A5_CONTEXT_QUALITY_WARNING"],
        "categories": ["UNKNOWN_TIMESTAMPS"],
        "candidate_counts": [],
    }
    assert result["recommended_actions"] == [
        "review_a1_unsupported_records_locally",
        "review_a5_quality_warnings_locally",
    ]
    assert "/private/example" not in serialized
    assert "999" not in serialized
    assert "PRIVATE-" not in serialized
    assert "future reason" not in serialized


def test_missing_reconciliation_is_explicit_not_guessed(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=0,
        unsupported=2,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
    )
    (tmp_path / "a1_staging" / "reconciliation.json").unlink()

    result = classify_review(report)

    assert result["review"]["unsupported_records"]["grouping_status"] == "UNAVAILABLE"
    assert result["review"]["unsupported_records"]["groups"] == []


def test_a5_unknown_details_remain_other(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=0,
        issues=[
            {
                "severity": "WARNING",
                "code": "A5_CONTEXT_QUALITY_WARNING",
                "detail": "future private detail /private/example/secret 999",
            }
        ],
    )

    result = classify_review(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["review"]["a5_quality"]["categories"] == ["OTHER"]
    assert "/private/example" not in serialized
    assert "999" not in serialized


def test_a5_candidate_counts_are_allowlisted_and_private_fields_are_redacted(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=0,
        issues=[
            {
                "severity": "WARNING",
                "code": "A5_CONTEXT_QUALITY_WARNING",
                "detail": "A5 selected 240 messages although max_messages=180 because candidate evidence is never silently removed.",
            }
        ],
        a5_checked=[
            {
                "candidate_type": "lexical_topic",
                "context_message_count": 240,
                "available_message_count": 510,
                "omitted_message_count": 270,
                "evidence_message_count": 240,
                "candidate_id": "PRIVATE-CANDIDATE-ID",
                "message_id": "PRIVATE-MESSAGE-ID",
                "path": "/private/example/secret",
            },
            {
                "candidate_type": "future-private-type",
                "context_message_count": "8",
                "available_message_count": "9",
                "omitted_message_count": "1",
                "evidence_message_count": "2",
                "candidate_id": "PRIVATE-OTHER-ID",
            },
        ],
    )

    result = classify_review(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["review"]["a5_quality"]["categories"] == ["EVIDENCE_EXCEEDS_CONTEXT_LIMIT"]
    assert result["review"]["a5_quality"]["candidate_counts"] == [
        {
            "candidate_type": "lexical_topic",
            "context_message_count": 240,
            "available_message_count": 510,
            "omitted_message_count": 270,
            "evidence_message_count": 240,
        },
        {
            "candidate_type": "OTHER",
            "context_message_count": 8,
            "available_message_count": 9,
            "omitted_message_count": 1,
            "evidence_message_count": 2,
        },
    ]
    assert "PRIVATE-" not in serialized
    assert "/private/example" not in serialized
