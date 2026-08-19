from __future__ import annotations

import json
from pathlib import Path
import unicodedata

import pytest

from tools.real_archive_attachment_review import (
    AttachmentReviewError,
    audit_attachment_resolution,
)


def _write_run(
    root: Path,
    attachments_root: Path,
    attachments: list[dict[str, object]],
    *,
    manifest_missing: int | None = None,
) -> Path:
    run = root / "run"
    staging = run / "a1_staging"
    staging.mkdir(parents=True)
    (staging / "manifest.json").write_text(
        json.dumps(
            {
                "attachments": {"root": str(attachments_root)},
                "outputs": {"messages": "messages.jsonl"},
                "counts": {
                    "attachments_missing": (
                        len(attachments) if manifest_missing is None else manifest_missing
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    (staging / "messages.jsonl").write_text(
        json.dumps(
            {
                "record_type": "message",
                "text": "PRIVATE-MESSAGE-TEXT",
                "attachments": attachments,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    report = run / "real_archive_report.json"
    report.write_text("{}\n", encoding="utf-8")
    return report


def _missing(path: str, *, size: int | None = None, identifier: str = "PRIVATE-ID") -> dict[str, object]:
    return {
        "source_attachment_id": identifier,
        "source_path": path,
        "filename": path,
        "transfer_name": "PRIVATE-TRANSFER-NAME",
        "total_bytes": size,
        "resolution_status": "missing",
    }


def test_audit_classifies_recoverable_and_absent_paths_without_leaking_private_values(
    tmp_path: Path,
):
    attachments_root = tmp_path / "Attachments"

    percent_file = attachments_root / "aa" / "My Photo.jpg"
    percent_file.parent.mkdir(parents=True)
    percent_file.write_bytes(b"percent")

    nfc_name = "caf\u00e9.jpg"
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    unicode_file = attachments_root / "bb" / nfc_name
    unicode_file.parent.mkdir(parents=True)
    unicode_file.write_bytes(b"unicode")

    # macOS filesystems may resolve an NFD lookup to an NFC-created filename
    # before the explicit Unicode-normalization branch is reached. Linux
    # filesystems normally keep the byte-distinct names separate. Both outcomes
    # are intentionally classified as exact/recoverable by the production audit.
    raw_unicode_candidate = attachments_root / "bb" / nfd_name
    unicode_category = (
        "CURRENT_PATH_NOW_EXISTS"
        if raw_unicode_candidate.is_file()
        else "UNICODE_NFC_EXACT"
    )

    relocated_file = attachments_root / "new" / "moved-private.jpg"
    relocated_file.parent.mkdir(parents=True)
    relocated_file.write_bytes(b"relocated")

    ambiguous_a = attachments_root / "x" / "ambiguous-private.jpg"
    ambiguous_b = attachments_root / "y" / "ambiguous-private.jpg"
    ambiguous_a.parent.mkdir(parents=True)
    ambiguous_b.parent.mkdir(parents=True)
    ambiguous_a.write_bytes(b"a")
    ambiguous_b.write_bytes(b"b")

    records = [
        _missing("~/Library/Messages/Attachments/aa/My%20Photo.jpg", identifier="PRIVATE-PERCENT"),
        _missing(
            f"~/Library/Messages/Attachments/bb/{nfd_name}",
            identifier="PRIVATE-UNICODE",
        ),
        _missing(
            "~/Library/Messages/Attachments/old/moved-private.jpg",
            size=len(b"relocated"),
            identifier="PRIVATE-RELOCATED",
        ),
        _missing(
            "~/Library/Messages/Attachments/old/ambiguous-private.jpg",
            identifier="PRIVATE-AMBIGUOUS",
        ),
        _missing(
            "~/Library/Messages/Attachments/old/absent-private.jpg",
            identifier="PRIVATE-ABSENT",
        ),
    ]
    report = _write_run(tmp_path, attachments_root, records)

    result = audit_attachment_resolution(report)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["contract"] == "real-archive-attachment-review-v1"
    assert result["status"] == "PASS"
    assert result["missing_occurrence_count"] == 5
    assert result["missing_unique_source_path_count"] == 5
    assert result["resolution_category_counts"] == {
        "BASENAME_AMBIGUOUS": 1,
        "BASENAME_UNIQUE_MATCH": 1,
        unicode_category: 1,
        "NOT_FOUND": 1,
        "PERCENT_DECODE_EXACT": 1,
    }
    assert result["summary"] == {
        "exact_normalization_recoverable_count": 2,
        "relocated_unique_candidate_count": 1,
        "ambiguous_candidate_count": 1,
        "not_found_count": 1,
        "resolver_fix_indicated": True,
        "relocation_investigation_indicated": True,
        "physical_absence_likely": False,
    }
    assert result["privacy"] == {
        "filenames_emitted": False,
        "source_ids_emitted": False,
        "paths_emitted": False,
        "message_text_emitted": False,
    }
    for private_value in (
        "PRIVATE-",
        "My Photo.jpg",
        "moved-private.jpg",
        "ambiguous-private.jpg",
        "absent-private.jpg",
        str(tmp_path),
    ):
        assert private_value not in serialized


def test_file_url_shape_is_allowlisted_and_relocation_is_detected(tmp_path: Path):
    attachments_root = tmp_path / "Attachments"
    target = attachments_root / "actual" / "file-url-private.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    report = _write_run(
        tmp_path,
        attachments_root,
        [
            _missing(
                "file:///old/Library/Messages/Attachments/stale/file-url-private.bin",
                size=1,
            )
        ],
    )

    result = audit_attachment_resolution(report)

    assert result["path_shape_counts"] == {"FILE_URL": 1}
    assert result["resolution_category_counts"] == {"BASENAME_UNIQUE_MATCH": 1}
    assert result["summary"]["relocation_investigation_indicated"] is True


def test_all_absent_paths_are_reported_as_likely_physical_absence(tmp_path: Path):
    attachments_root = tmp_path / "Attachments"
    attachments_root.mkdir()
    report = _write_run(
        tmp_path,
        attachments_root,
        [
            _missing("~/Library/Messages/Attachments/aa/PRIVATE-A.bin"),
            _missing("~/Library/Messages/Attachments/bb/PRIVATE-B.bin"),
        ],
    )

    result = audit_attachment_resolution(report)
    serialized = json.dumps(result)

    assert result["resolution_category_counts"] == {"NOT_FOUND": 2}
    assert result["summary"]["physical_absence_likely"] is True
    assert "PRIVATE-A" not in serialized
    assert "PRIVATE-B" not in serialized


def test_manifest_count_mismatch_fails_closed(tmp_path: Path):
    attachments_root = tmp_path / "Attachments"
    attachments_root.mkdir()
    report = _write_run(
        tmp_path,
        attachments_root,
        [_missing("missing-private.bin")],
        manifest_missing=2,
    )

    with pytest.raises(AttachmentReviewError, match="manifest missing count"):
        audit_attachment_resolution(report)


def test_explicit_root_can_replace_manifest_root_without_being_emitted(tmp_path: Path):
    attachments_root = tmp_path / "PRIVATE-ROOT"
    attachments_root.mkdir()
    run_root = tmp_path / "case"
    report = _write_run(
        run_root,
        tmp_path / "DOES-NOT-EXIST",
        [_missing("PRIVATE-MISSING.bin")],
    )

    result = audit_attachment_resolution(report, attachments_root=attachments_root)
    serialized = json.dumps(result)

    assert result["status"] == "PASS"
    assert result["resolution_category_counts"] == {"NOT_FOUND": 1}
    assert "PRIVATE-ROOT" not in serialized
    assert "PRIVATE-MISSING" not in serialized
