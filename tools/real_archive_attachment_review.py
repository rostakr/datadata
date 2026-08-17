from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path, PurePosixPath
import unicodedata
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse


class AttachmentReviewError(RuntimeError):
    pass


_PATH_SHAPES = {
    "FILE_URL",
    "TILDE_MESSAGES_ATTACHMENTS",
    "ABSOLUTE_MESSAGES_ATTACHMENTS",
    "RELATIVE_ATTACHMENTS_PREFIX",
    "RELATIVE_OTHER",
    "ABSOLUTE_OTHER",
    "OTHER",
}

_RESOLUTION_CATEGORIES = {
    "CURRENT_PATH_NOW_EXISTS",
    "PERCENT_DECODE_EXACT",
    "UNICODE_NFC_EXACT",
    "UNICODE_NFD_EXACT",
    "BASENAME_UNIQUE_MATCH",
    "BASENAME_AMBIGUOUS",
    "NOT_FOUND",
}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AttachmentReviewError(f"Required file not found: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise AttachmentReviewError(f"Invalid JSON in {path.name}") from exc
    if not isinstance(value, dict):
        raise AttachmentReviewError(f"Expected JSON object in {path.name}")
    return value


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalized_raw_path(raw_path: str) -> str:
    if raw_path.casefold().startswith("file://"):
        parsed = urlparse(raw_path)
        return parsed.path.replace("\\", "/")
    return raw_path.replace("\\", "/")


def _path_shape(raw_path: str) -> str:
    if raw_path.casefold().startswith("file://"):
        return "FILE_URL"
    normalized = raw_path.replace("\\", "/")
    folded = normalized.casefold()
    if folded.startswith("~/library/messages/attachments/"):
        return "TILDE_MESSAGES_ATTACHMENTS"
    if normalized.startswith("/") and "/library/messages/attachments/" in folded:
        return "ABSOLUTE_MESSAGES_ATTACHMENTS"
    parts = [part.casefold() for part in PurePosixPath(normalized).parts]
    if "attachments" in parts and not normalized.startswith("/") and not normalized.startswith("~"):
        return "RELATIVE_ATTACHMENTS_PREFIX"
    if normalized.startswith("/"):
        return "ABSOLUTE_OTHER"
    if not normalized.startswith("~"):
        return "RELATIVE_OTHER"
    return "OTHER"


def _suffix_after_attachments(raw_path: str) -> tuple[str, ...] | None:
    normalized = _normalized_raw_path(raw_path)
    parts = PurePosixPath(normalized).parts
    lower = [part.casefold() for part in parts]
    if "attachments" not in lower:
        return None
    idx = lower.index("attachments")
    suffix = tuple(parts[idx + 1 :])
    return suffix or None


def _root_candidate(root: Path, raw_path: str) -> Path | None:
    suffix = _suffix_after_attachments(raw_path)
    if suffix:
        return root.joinpath(*suffix)
    normalized = _normalized_raw_path(raw_path)
    path = Path(normalized)
    if not path.is_absolute() and not normalized.startswith("~"):
        return root / path
    return None


def _current_candidates(root: Path, raw_path: str) -> list[Path]:
    result: list[Path] = []
    normalized = _normalized_raw_path(raw_path)
    if raw_path.casefold().startswith("file://"):
        result.append(Path(normalized))
    else:
        result.append(Path(raw_path).expanduser())
    rooted = _root_candidate(root, raw_path)
    if rooted is not None and rooted not in result:
        result.append(rooted)
    return result


def _normalized_suffix_candidate(root: Path, raw_path: str, form: str) -> Path | None:
    decoded = unquote(raw_path)
    suffix = _suffix_after_attachments(decoded)
    if suffix is None:
        normalized = _normalized_raw_path(decoded)
        path = Path(normalized)
        if path.is_absolute() or normalized.startswith("~"):
            return None
        suffix = tuple(PurePosixPath(normalized).parts)
    normalized_parts = tuple(unicodedata.normalize(form, part) for part in suffix)
    return root.joinpath(*normalized_parts)


def _basename_keys(raw_path: str) -> set[str]:
    normalized = _normalized_raw_path(unquote(raw_path))
    name = PurePosixPath(normalized).name
    if not name:
        return set()
    return {
        name,
        unicodedata.normalize("NFC", name),
        unicodedata.normalize("NFD", name),
    }


def _build_basename_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        for key in {
            path.name,
            unicodedata.normalize("NFC", path.name),
            unicodedata.normalize("NFD", path.name),
        }:
            index[key].append(path)
    return index


def _safe_size_match(paths: set[Path], total_bytes: object) -> set[Path]:
    expected = _count(total_bytes)
    if expected <= 0 or len(paths) <= 1:
        return paths
    matched: set[Path] = set()
    for path in paths:
        try:
            if path.stat().st_size == expected:
                matched.add(path)
        except OSError:
            continue
    return matched or paths


def _classify_missing(
    root: Path,
    raw_path: str,
    total_bytes: object,
    basename_index: Mapping[str, list[Path]],
) -> str:
    for candidate in _current_candidates(root, raw_path):
        if candidate.is_file():
            return "CURRENT_PATH_NOW_EXISTS"

    decoded = unquote(raw_path)
    if decoded != raw_path:
        candidate = _root_candidate(root, decoded)
        if candidate is not None and candidate.is_file():
            return "PERCENT_DECODE_EXACT"
        if decoded.casefold().startswith("file://"):
            file_candidate = Path(_normalized_raw_path(decoded))
            if file_candidate.is_file():
                return "PERCENT_DECODE_EXACT"

    nfc_candidate = _normalized_suffix_candidate(root, raw_path, "NFC")
    if nfc_candidate is not None and nfc_candidate.is_file():
        return "UNICODE_NFC_EXACT"
    nfd_candidate = _normalized_suffix_candidate(root, raw_path, "NFD")
    if nfd_candidate is not None and nfd_candidate.is_file():
        return "UNICODE_NFD_EXACT"

    basename_matches: set[Path] = set()
    for key in _basename_keys(raw_path):
        basename_matches.update(basename_index.get(key, []))
    basename_matches = _safe_size_match(basename_matches, total_bytes)
    if len(basename_matches) == 1:
        return "BASENAME_UNIQUE_MATCH"
    if len(basename_matches) > 1:
        return "BASENAME_AMBIGUOUS"
    return "NOT_FOUND"


def _iter_missing_attachments(messages_path: Path):
    try:
        stream = messages_path.open("r", encoding="utf-8")
    except FileNotFoundError as exc:
        raise AttachmentReviewError(f"Required file not found: {messages_path.name}") from exc
    with stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AttachmentReviewError(
                    f"Invalid JSONL record in {messages_path.name} at line {line_number}"
                ) from exc
            if not isinstance(record, Mapping):
                continue
            attachments = record.get("attachments") or []
            if not isinstance(attachments, list):
                continue
            for attachment in attachments:
                if not isinstance(attachment, Mapping):
                    continue
                if str(attachment.get("resolution_status") or "") != "missing":
                    continue
                raw_path = attachment.get("source_path") or attachment.get("filename")
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                yield raw_path, attachment.get("total_bytes")


def audit_attachment_resolution(
    report_path: str | Path,
    *,
    attachments_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audit unresolved attachment paths without exposing their private values."""

    report = Path(report_path).expanduser().resolve()
    staging = report.parent / "a1_staging"
    manifest = _read_object(staging / "manifest.json")
    outputs = manifest.get("outputs") or {}
    if not isinstance(outputs, Mapping):
        outputs = {}
    messages_name = str(outputs.get("messages") or "messages.jsonl")
    messages_path = staging / messages_name

    manifest_attachments = manifest.get("attachments") or {}
    if not isinstance(manifest_attachments, Mapping):
        manifest_attachments = {}
    root_value = attachments_root or manifest_attachments.get("root")
    if not root_value:
        raise AttachmentReviewError("Attachments root is not available")
    root = Path(str(root_value)).expanduser().resolve()
    if not root.is_dir():
        raise AttachmentReviewError("Attachments root is not a directory")

    counts = manifest.get("counts") or {}
    if not isinstance(counts, Mapping):
        counts = {}
    expected_missing = _count(counts.get("attachments_missing"))

    missing = list(_iter_missing_attachments(messages_path))
    if len(missing) != expected_missing:
        raise AttachmentReviewError("A1 manifest missing count does not match staging records")

    basename_index = _build_basename_index(root)
    shape_counts: Counter[str] = Counter()
    resolution_counts: Counter[str] = Counter()
    unique_private_paths: set[str] = set()

    for raw_path, total_bytes in missing:
        shape = _path_shape(raw_path)
        if shape not in _PATH_SHAPES:
            shape = "OTHER"
        category = _classify_missing(root, raw_path, total_bytes, basename_index)
        if category not in _RESOLUTION_CATEGORIES:
            category = "NOT_FOUND"
        shape_counts[shape] += 1
        resolution_counts[category] += 1
        unique_private_paths.add(raw_path)

    exact_normalization_matches = sum(
        resolution_counts[name]
        for name in (
            "CURRENT_PATH_NOW_EXISTS",
            "PERCENT_DECODE_EXACT",
            "UNICODE_NFC_EXACT",
            "UNICODE_NFD_EXACT",
        )
    )
    relocated_unique = resolution_counts["BASENAME_UNIQUE_MATCH"]
    ambiguous = resolution_counts["BASENAME_AMBIGUOUS"]
    not_found = resolution_counts["NOT_FOUND"]

    return {
        "contract": "real-archive-attachment-review-v1",
        "status": "PASS",
        "missing_occurrence_count": len(missing),
        "missing_unique_source_path_count": len(unique_private_paths),
        "path_shape_counts": {
            key: shape_counts[key] for key in sorted(_PATH_SHAPES) if shape_counts[key]
        },
        "resolution_category_counts": {
            key: resolution_counts[key]
            for key in sorted(_RESOLUTION_CATEGORIES)
            if resolution_counts[key]
        },
        "summary": {
            "exact_normalization_recoverable_count": exact_normalization_matches,
            "relocated_unique_candidate_count": relocated_unique,
            "ambiguous_candidate_count": ambiguous,
            "not_found_count": not_found,
            "resolver_fix_indicated": exact_normalization_matches > 0,
            "relocation_investigation_indicated": relocated_unique > 0,
            "physical_absence_likely": (
                len(missing) > 0
                and exact_normalization_matches == 0
                and relocated_unique == 0
                and ambiguous == 0
                and not_found == len(missing)
            ),
        },
        "privacy": {
            "filenames_emitted": False,
            "source_ids_emitted": False,
            "paths_emitted": False,
            "message_text_emitted": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.real_archive_attachment_review",
        description=(
            "Read-only privacy-safe diagnosis of A1 attachment paths from an existing real-archive run."
        ),
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--attachments-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = audit_attachment_resolution(
            args.report,
            attachments_root=args.attachments_root,
        )
    except AttachmentReviewError as exc:
        print(
            json.dumps(
                {
                    "contract": "real-archive-attachment-review-v1",
                    "status": "FAIL",
                    "code": "ATTACHMENT_REVIEW_INPUT_INVALID",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
