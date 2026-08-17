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


def test_review_summary_keeps_warning_categories_but_redacts_private_context(tmp_path: Path):
    report = _write_case(
        tmp_path,
        attachment_root=None,
        missing=0,
        unsupported=4,
        issues=[
            {
                "severity": "WARNING",
                "code": "A1_UNSUPPORTED_RECORDS_PRESENT",
                "detail": "synthetic",
            },
            {
                "severity": "WARNING",
                "code": "A5_CONTEXT_QUALITY_WARNING",
                "detail": "synthetic",
            },
        ],
    )

    result = classify_review(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["review"]["attachments"]["state"] == "NONE"
    assert result["review"]["unsupported_records"] == {"present": True, "count": 4}
    assert result["review"]["a5_quality"] == {
        "present": True,
        "warning_codes": ["A5_CONTEXT_QUALITY_WARNING"],
    }
    assert result["recommended_actions"] == [
        "review_a1_unsupported_records_locally",
        "review_a5_quality_warnings_locally",
    ]
    assert "/private/example" not in serialized
    assert "999" not in serialized
