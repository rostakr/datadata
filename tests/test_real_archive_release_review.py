from __future__ import annotations

import json
from pathlib import Path

from tools.real_archive_release_review import evaluate_release_policy


def _write_case(
    root: Path,
    *,
    unsupported: int,
    unsupported_records: list[dict[str, object]] | None = None,
    issues: list[dict[str, str]] | None = None,
    attachment_root: str | None = None,
    attachments_missing: int = 0,
    write_reconciliation: bool = True,
) -> Path:
    staging = root / "a1_staging"
    staging.mkdir(parents=True)
    (staging / "manifest.json").write_text(
        json.dumps(
            {
                "attachments": {"root": attachment_root},
                "counts": {
                    "attachments_missing": attachments_missing,
                    "unsupported": unsupported,
                },
            }
        ),
        encoding="utf-8",
    )
    if write_reconciliation:
        (staging / "reconciliation.json").write_text(
            json.dumps({"unsupported_records": unsupported_records or []}),
            encoding="utf-8",
        )
    report = root / "real_archive_report.json"
    report.write_text(
        json.dumps(
            {
                "status": "WARNING" if issues else "PASS",
                "verdict": "NEEDS_REVIEW" if issues else "VALID",
                "release_ready": not bool(issues),
                "issues": issues or [],
                "selector": {"conversation_id": 999},
                "source": {"path": "/private/example/chat.db"},
                "a5_probe": {"checked": []},
            }
        ),
        encoding="utf-8",
    )
    return report


def _benign(identifier: str) -> dict[str, object]:
    return {
        "record_type": "attachment",
        "source_identifier": identifier,
        "reason": "attachment row is not referenced by message_attachment_join",
    }


def test_benign_unreferenced_attachment_rows_do_not_block_release(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=2,
        unsupported_records=[_benign("PRIVATE-1"), _benign("PRIVATE-2")],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
    )
    before = report.read_bytes()

    result = evaluate_release_policy(report)

    assert result["contract"] == "real-archive-release-review-v1"
    assert result["base_gate_verdict"] == "NEEDS_REVIEW"
    assert result["verdict"] == "VALID"
    assert result["release_ready"] is True
    assert result["warning_codes"] == []
    assert result["review"]["unsupported_records"]["classification_complete"] is True
    assert result["review"]["unsupported_records"]["nonblocking_count"] == 2
    assert result["review"]["unsupported_records"]["blocking_count"] == 0
    assert "review_a1_unsupported_records_locally" not in result["recommended_actions"]
    assert report.read_bytes() == before


def test_broken_attachment_relation_remains_release_blocking(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=2,
        unsupported_records=[
            _benign("PRIVATE-1"),
            {
                "record_type": "message_attachment_join",
                "source_identifier": "PRIVATE-JOIN",
                "message_id": "PRIVATE-MESSAGE",
                "reason": "relation points to a missing attachment row",
            },
        ],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
    )

    result = evaluate_release_policy(report)

    assert result["verdict"] == "NEEDS_REVIEW"
    assert result["release_ready"] is False
    assert result["review"]["unsupported_records"]["nonblocking_count"] == 1
    assert result["review"]["unsupported_records"]["blocking_count"] == 1
    assert "A1_UNSUPPORTED_RECORDS_PRESENT" in result["warning_codes"]
    assert "review_a1_unsupported_records_locally" in result["recommended_actions"]


def test_unknown_or_incomplete_grouping_fails_closed(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=2,
        unsupported_records=None,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
        write_reconciliation=False,
    )

    result = evaluate_release_policy(report)

    assert result["verdict"] == "NEEDS_REVIEW"
    assert result["review"]["unsupported_records"]["classification_complete"] is False
    assert result["review"]["unsupported_records"]["blocking_count"] > 0
    assert "A1_UNSUPPORTED_CLASSIFICATION_INCOMPLETE" in result["warning_codes"]


def test_other_quality_warning_is_preserved_even_when_unsupported_is_benign(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=1,
        unsupported_records=[_benign("PRIVATE-1")],
        attachment_root="/private/example/Attachments",
        attachments_missing=3,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            },
            {
                "severity": "WARNING",
                "code": "A1_ATTACHMENTS_MISSING",
                "detail": "synthetic",
            },
        ],
    )

    result = evaluate_release_policy(report)

    assert result["verdict"] == "NEEDS_REVIEW"
    assert result["warning_codes"] == ["A1_ATTACHMENTS_MISSING"]
    assert result["review"]["attachments"]["state"] == "UNRESOLVED_WITH_ROOT"
    assert "inspect_unresolved_attachments_locally" in result["recommended_actions"]


def test_private_identifiers_are_not_exposed(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=2,
        unsupported_records=[
            _benign("PRIVATE-ATTACHMENT-ID"),
            {
                "record_type": "future_private_type",
                "source_identifier": "/private/example/secret",
                "reason": "future private reason 999",
            },
        ],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
    )

    result = evaluate_release_policy(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert "PRIVATE-" not in serialized
    assert "/private/example" not in serialized
    assert "future private reason" not in serialized
    assert "999" not in serialized
    assert result["review"]["unsupported_records"]["blocking_count"] == 1


def test_existing_gate_error_cannot_be_promoted(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=1,
        unsupported_records=[_benign("PRIVATE-1")],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            },
            {
                "severity": "ERROR",
                "code": "A5_CONTEXT_PROVENANCE_MISSING",
                "detail": "synthetic",
            },
        ],
    )

    result = evaluate_release_policy(report)

    assert result["verdict"] == "INVALID"
    assert result["release_ready"] is False
    assert result["error_codes"] == ["A5_CONTEXT_PROVENANCE_MISSING"]


def test_raw_invalid_verdict_cannot_be_promoted_without_explicit_error_code(tmp_path: Path):
    report = _write_case(
        tmp_path,
        unsupported=1,
        unsupported_records=[_benign("PRIVATE-1")],
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            }
        ],
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["status"] = "FAIL"
    payload["verdict"] = "INVALID"
    payload["release_ready"] = False
    report.write_text(json.dumps(payload), encoding="utf-8")

    result = evaluate_release_policy(report)

    assert result["base_gate_verdict"] == "INVALID"
    assert result["error_codes"] == []
    assert result["verdict"] == "INVALID"
    assert result["release_ready"] is False
