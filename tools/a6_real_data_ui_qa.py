from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

import pandas as pd

from a6.data import analysis_packet, filter_messages, load_sqlite_messages
from a6.evidence import (
    PacketProvenanceError,
    enrich_analysis_packet_source_provenance,
    load_current_message_provenance,
)
from a6.findings import filter_findings, load_a4_findings, resolve_evidence
from a6.metrics import load_a4_conversation_metrics
from tools.a6_viewport_smoke import EXPECTED_TABS, VIEWPORTS, _page_metrics


REAL_DATA_REQUIRED_TABS = (
    "Konverzace",
    "Grafy",
    "Významná období",
    "Vybrané zprávy",
    "Analýza",
)
SEMANTIC_UI_MARKERS = (
    "Deterministická metric evidence",
    "#### Pozorování",
    "#### Interpretace",
    "#### Vzorce",
    "#### Alternativní vysvětlení",
    "#### Nejistoty / chybějící informace",
)
_FORBIDDEN_REPORT_KEYS = {
    "absolute_path",
    "contact",
    "conversation_id",
    "finding_id",
    "message_id",
    "membership_id",
    "participant_id",
    "sender",
    "source_message_id",
    "source_record_key",
    "source_snapshot_key",
    "text",
}


@dataclass(frozen=True)
class _TargetContext:
    contact: str
    conversation_id: str
    conversation_frame: pd.DataFrame
    period_frame: pd.DataFrame
    finding_option_label: str
    evidence_message_ids: tuple[str, ...]


def _database_label(path: Path) -> str:
    """Return a report-safe identifier that never exposes the absolute archive path."""

    return path.name


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= int(response.status) < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Streamlit health endpoint did not become ready: {last_error}")


def _finding_option_label(row: Any) -> str:
    when = "čas neznámý"
    if row.start_timestamp is not None and not pd.isna(row.start_timestamp):
        when = pd.Timestamp(row.start_timestamp).strftime("%Y-%m-%d")
    return f"{when} · {row.finding_type} · {row.label} · score {float(row.score):.2f}"


def _select_target_context(database: Path, explicit_conversation_id: str | None = None) -> _TargetContext:
    frame, _ = load_sqlite_messages(database)
    if frame.empty:
        raise RuntimeError("Canonical SQLite database contains no usable message rows.")

    findings = load_a4_findings(database)
    summary = (
        frame.groupby(["contact", "conversation_id"], dropna=False)
        .agg(
            memberships=("membership_id", "count"),
            canonical_messages=("message_id", "nunique"),
        )
        .reset_index()
    )
    summary["conversation_id"] = summary["conversation_id"].astype(str)
    summary["contact"] = summary["contact"].astype(str)

    finding_scores: dict[str, tuple[int, int]] = {}
    if not findings.empty:
        for conversation_id, group in findings.groupby(findings["conversation_id"].astype(str), sort=False):
            evidence_count = sum(bool(tuple(value or ())) for value in group["evidence_message_ids"])
            finding_scores[str(conversation_id)] = (int(evidence_count), int(len(group)))

    summary["_evidence_findings"] = summary["conversation_id"].map(
        lambda value: finding_scores.get(str(value), (0, 0))[0]
    )
    summary["_finding_count"] = summary["conversation_id"].map(
        lambda value: finding_scores.get(str(value), (0, 0))[1]
    )

    if explicit_conversation_id is not None:
        candidates = summary[summary["conversation_id"] == str(explicit_conversation_id)]
        if candidates.empty:
            raise RuntimeError("Requested canonical conversation_id is not present in the database.")
        summary = candidates

    summary = summary.sort_values(
        [
            "_evidence_findings",
            "_finding_count",
            "memberships",
            "canonical_messages",
            "contact",
            "conversation_id",
        ],
        ascending=[False, False, False, False, True, True],
        kind="stable",
    )
    selected = summary.iloc[0]
    contact = str(selected["contact"])
    conversation_id = str(selected["conversation_id"])
    conversation_frame = frame[
        (frame["contact"].astype(str) == contact)
        & (frame["conversation_id"].astype(str) == conversation_id)
    ].reset_index(drop=True)

    known = conversation_frame[conversation_frame["timestamp"].notna()].reset_index(drop=True)
    if known.empty:
        raise RuntimeError("Selected real-data conversation has no known timestamps.")
    start_index = len(known) // 4
    end_index = max(start_index, (len(known) * 3) // 4)
    start = known.iloc[start_index]["timestamp"]
    end = known.iloc[end_index]["timestamp"]
    period_frame = filter_messages(
        conversation_frame,
        start=start,
        end=end,
        include_unknown_timestamps=False,
    )
    if period_frame.empty:
        raise RuntimeError("Deterministic real-data period filter produced no message rows.")

    relevant = filter_findings(findings, [conversation_id])
    chosen_finding = None
    evidence_ids: tuple[str, ...] = ()
    for row in relevant.itertuples(index=False):
        ids = tuple(str(value) for value in (row.evidence_message_ids or ()))
        if not ids:
            continue
        evidence, missing = resolve_evidence(conversation_frame, ids)
        if not evidence.empty and not missing:
            chosen_finding = row
            evidence_ids = tuple(evidence["message_id"].astype(str))
            break
    if chosen_finding is None or not evidence_ids:
        raise RuntimeError("Selected real-data conversation has no resolvable A4 finding evidence.")

    return _TargetContext(
        contact=contact,
        conversation_id=conversation_id,
        conversation_frame=conversation_frame,
        period_frame=period_frame,
        finding_option_label=_finding_option_label(chosen_finding),
        evidence_message_ids=evidence_ids,
    )


def _semantic_ui_contract() -> bool:
    app_path = Path(__file__).resolve().parents[1] / "a6" / "app_legacy.py"
    source = app_path.read_text(encoding="utf-8")
    return all(marker in source for marker in SEMANTIC_UI_MARKERS)


def _build_data_checks(database: Path, target: _TargetContext) -> dict[str, Any]:
    errors: list[str] = []
    metrics = load_a4_conversation_metrics(database, target.conversation_id)
    findings = load_a4_findings(database)
    relevant = filter_findings(findings, [target.conversation_id])

    evidence, missing = resolve_evidence(
        target.conversation_frame,
        target.evidence_message_ids,
    )
    if missing or evidence.empty:
        errors.append("evidence_resolution_failed")

    provenance_complete = False
    try:
        current_sources = load_current_message_provenance(
            database,
            target.evidence_message_ids,
        )
        provenance_complete = all(
            message_id in current_sources
            and any(
                row.get("source_record_key") and row.get("source_snapshot_key")
                for row in current_sources[message_id]
            )
            for message_id in target.evidence_message_ids
        )
    except PacketProvenanceError:
        errors.append("source_provenance_query_failed")

    a5_packet_complete = False
    try:
        packet = analysis_packet(
            target.conversation_frame,
            target.evidence_message_ids,
            context_before=0,
            context_after=0,
        )
        packet = enrich_analysis_packet_source_provenance(
            packet,
            database,
            require_provenance=True,
        )
        a5_packet_complete = packet.get("source_provenance_status") == "complete"
    except (PacketProvenanceError, ValueError):
        errors.append("a5_packet_provenance_failed")

    period_is_narrower = 0 < len(target.period_frame) < len(target.conversation_frame)
    semantic_separation = _semantic_ui_contract()
    checks = {
        "canonical_memberships": int(len(target.conversation_frame)),
        "canonical_messages": int(target.conversation_frame["message_id"].nunique()),
        "period_filtered_memberships": int(len(target.period_frame)),
        "period_filter_nonempty": bool(len(target.period_frame)),
        "period_is_narrower": bool(period_is_narrower),
        "a4_metrics_available": bool(metrics.available),
        "a4_findings_count": int(len(relevant)),
        "evidence_message_count": int(len(target.evidence_message_ids)),
        "evidence_resolved": bool(not missing and not evidence.empty),
        "source_provenance_complete": bool(provenance_complete),
        "a5_packet_provenance_complete": bool(a5_packet_complete),
        "semantic_separation_contract": bool(semantic_separation),
        "errors": errors,
    }
    required_flags = (
        checks["period_filter_nonempty"],
        checks["period_is_narrower"],
        checks["a4_metrics_available"],
        checks["a4_findings_count"] > 0,
        checks["evidence_message_count"] > 0,
        checks["evidence_resolved"],
        checks["source_provenance_complete"],
        checks["a5_packet_provenance_complete"],
        checks["semantic_separation_contract"],
        not errors,
    )
    checks["status"] = "PASS" if all(required_flags) else "FAIL"
    return checks


def _private_values(target: _TargetContext) -> tuple[str, ...]:
    values = {
        target.contact.strip(),
        target.finding_option_label.strip(),
    }
    for value in target.conversation_frame["sender"].dropna().astype(str).unique():
        values.add(value.strip())
    for value in target.conversation_frame["text"].dropna().astype(str):
        text = value.strip()
        if len(text) >= 12:
            values.add(text[:80])
        if len(values) >= 40:
            break
    return tuple(value for value in values if len(value) >= 4)


def _assert_report_privacy(
    report: dict[str, Any],
    *,
    database: Path,
    private_values: Sequence[str] = (),
) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key) in _FORBIDDEN_REPORT_KEYS:
                    raise RuntimeError(f"Privacy contract violation: forbidden report key {key!r}")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True)
    absolute = str(database.expanduser().resolve())
    if absolute in payload:
        raise RuntimeError("Privacy contract violation: absolute database path leaked into report")
    for value in private_values:
        if value and value in payload:
            raise RuntimeError("Privacy contract violation: private data leaked into report")


def _select_combobox_value(page: Any, label: str, value: str, timeout_ms: int) -> bool:
    combobox = page.get_by_role("combobox", name=label, exact=True)
    if combobox.count() == 0:
        return False
    combobox.first.click(timeout=timeout_ms)
    option = page.get_by_role("option", name=value, exact=True)
    option.wait_for(state="visible", timeout=timeout_ms)
    option.click(timeout=timeout_ms)
    page.wait_for_timeout(600)
    return True


def _select_target_in_ui(page: Any, target: _TargetContext, timeout_ms: int) -> None:
    if not _select_combobox_value(page, "Kontakt", target.contact, timeout_ms):
        raise RuntimeError("Contact selector is not available in A6.")

    conversation_box = page.get_by_role("combobox", name="Konverzace", exact=True)
    if conversation_box.count():
        conversation_box.first.click(timeout=timeout_ms)
        options = page.get_by_role("option")
        labels = [label.strip() for label in options.all_inner_texts()]
        prefix = f"{target.conversation_id} ·"
        matching = next((label for label in labels if label.startswith(prefix)), None)
        if matching is None:
            raise RuntimeError("Canonical conversation is not selectable in A6.")
        page.get_by_role("option", name=matching, exact=True).click(timeout=timeout_ms)
        page.wait_for_timeout(600)
    else:
        marker = page.get_by_text(f"conversation_id: `{target.conversation_id}`", exact=False)
        if marker.count() == 0:
            raise RuntimeError("A6 did not resolve the expected canonical conversation.")


def _select_finding_in_ui(page: Any, target: _TargetContext, timeout_ms: int) -> None:
    combobox = page.get_by_role("combobox", name="Analytický nález", exact=True)
    combobox.wait_for(state="visible", timeout=timeout_ms)
    combobox.click(timeout=timeout_ms)
    option = page.get_by_role("option", name=target.finding_option_label, exact=True)
    option.wait_for(state="visible", timeout=timeout_ms)
    option.click(timeout=timeout_ms)
    page.wait_for_timeout(600)


def _select_sqlite_source(
    page: Any,
    database: Path,
    timeout_ms: int,
    target: _TargetContext,
) -> None:
    radio = page.get_by_role("radio", name="SQLite", exact=True)
    radio.wait_for(state="attached", timeout=timeout_ms)
    radio.click(timeout=timeout_ms)

    textbox = page.get_by_role("textbox", name="SQLite", exact=True)
    textbox.wait_for(state="visible", timeout=timeout_ms)
    textbox.fill(str(database))
    textbox.press("Enter")
    page.wait_for_timeout(800)
    page.get_by_role("heading", name="Analýza zpráv", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    _select_target_in_ui(page, target, timeout_ms)


def _exercise_real_interactions(
    page: Any,
    target: _TargetContext,
    timeout_ms: int,
) -> dict[str, bool]:
    checks = {
        "period_control": False,
        "conversation_messages": False,
        "a4_metrics": False,
        "finding_evidence": False,
        "selected_evidence": False,
        "analysis_packet": False,
    }

    checks["period_control"] = page.get_by_text("Období", exact=True).count() > 0

    page.get_by_role("tab", name="Konverzace", exact=True).click(timeout=timeout_ms)
    page.get_by_text("Vybrat zprávy pro analýzu", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    page.get_by_text("membership_id:", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["conversation_messages"] = True

    page.get_by_role("tab", name="Grafy", exact=True).click(timeout=timeout_ms)
    page.get_by_text("Zdroj metrik: A4 latest-run views", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["a4_metrics"] = True

    page.get_by_role("tab", name="Významná období", exact=True).click(timeout=timeout_ms)
    _select_finding_in_ui(page, target, timeout_ms)
    page.get_by_text("Message source provenance", exact=True).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    button = page.get_by_role(
        "button",
        name="Použít evidence tohoto nálezu pro AI analýzu",
        exact=True,
    )
    button.wait_for(state="visible", timeout=timeout_ms)
    checks["finding_evidence"] = True
    button.click(timeout=timeout_ms)
    page.wait_for_timeout(900)

    page.get_by_role("tab", name="Vybrané zprávy", exact=True).click(timeout=timeout_ms)
    page.get_by_text("Aktivní zdroj výběru: A4 nález", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    page.get_by_text("Message source provenance", exact=True).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["selected_evidence"] = True

    page.get_by_role("tab", name="Analýza", exact=True).click(timeout=timeout_ms)
    page.get_by_text("Aktivní zdroj výběru: A4 nález", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    page.get_by_text("A6 neposílá celý archiv do AI.", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    page.get_by_text("Lokální AI analýza", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["analysis_packet"] = True
    return checks


def run_real_data_ui_qa(
    *,
    database: Path,
    output_dir: Path,
    timeout_ms: int = 30_000,
    keep_screenshots: bool = False,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Canonical SQLite database does not exist: {database}")

    target = _select_target_context(database, conversation_id)
    data_checks = _build_data_checks(database, target)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for real-data A6 browser QA") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    health_url = f"{url}/_stcore/health"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    report: dict[str, Any] = {
        "contract": "a6-real-data-browser-v2",
        "database": _database_label(database),
        "expected_tabs": EXPECTED_TABS,
        "required_interaction_tabs": list(REAL_DATA_REQUIRED_TABS),
        "screenshots_retained": bool(keep_screenshots),
        "data_checks": data_checks,
        "cases": [],
        "status": "PASS" if data_checks["status"] == "PASS" else "FAIL",
    }

    try:
        _wait_for_health(health_url, timeout_seconds=max(10.0, timeout_ms / 1000))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for case in VIEWPORTS:
                    context = browser.new_context(viewport={"width": case.width, "height": case.height})
                    page = context.new_page()
                    errors: list[str] = []
                    page_errors: list[str] = []
                    page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(type(exc).__name__))
                    screenshot_name: str | None = None
                    metrics: dict[str, Any] = {}
                    interaction_checks: dict[str, bool] = {}
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                        page.get_by_role("heading", name="Analýza zpráv", exact=True).wait_for(
                            state="visible", timeout=timeout_ms
                        )
                        _select_sqlite_source(page, database, timeout_ms, target)

                        exception_count = page.locator('[data-testid="stException"]').count()
                        if exception_count:
                            errors.append(f"streamlit_exception_count={exception_count}")

                        tabs = page.get_by_role("tab")
                        tab_labels = [label.strip() for label in tabs.all_inner_texts()]
                        if tab_labels != EXPECTED_TABS:
                            errors.append("tab_labels_mismatch")

                        interaction_checks = _exercise_real_interactions(page, target, timeout_ms)
                        for name, passed in interaction_checks.items():
                            if not passed:
                                errors.append(f"interaction_failed={name}")

                        metrics = _page_metrics(page)
                        overflow_px = int(metrics.get("page_horizontal_overflow_px") or 0)
                        if overflow_px > 2:
                            errors.append(f"page_horizontal_overflow_px={overflow_px}")
                        metric_count = int(metrics.get("metric_count") or 0)
                        if metric_count != 6:
                            errors.append(f"metric_count={metric_count}, expected=6")
                        max_same_row = int(metrics.get("max_metrics_same_row") or 0)
                        if max_same_row > case.max_metrics_per_row:
                            errors.append(
                                f"max_metrics_same_row={max_same_row}, allowed={case.max_metrics_per_row}"
                            )

                        if keep_screenshots:
                            screenshot = output_dir / f"{case.name}.png"
                            page.screenshot(path=str(screenshot), full_page=True)
                            screenshot_name = screenshot.name
                    except Exception as exc:
                        errors.append(f"browser_check_error={type(exc).__name__}")
                        if keep_screenshots:
                            screenshot = output_dir / f"{case.name}-failure.png"
                            try:
                                page.screenshot(path=str(screenshot), full_page=True)
                                screenshot_name = screenshot.name
                            except Exception:
                                screenshot_name = None
                    finally:
                        context.close()

                    if page_errors:
                        errors.append(f"pageerror_count={len(page_errors)}")
                    case_report = {
                        "name": case.name,
                        "width": case.width,
                        "height": case.height,
                        "max_metrics_per_row": case.max_metrics_per_row,
                        "metrics": metrics,
                        "interaction_checks": interaction_checks,
                        "errors": errors,
                        "status": "PASS" if not errors else "FAIL",
                        "screenshot": screenshot_name,
                    }
                    report["cases"].append(case_report)
                    if errors:
                        report["status"] = "FAIL"
            finally:
                browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    _assert_report_privacy(
        report,
        database=database,
        private_values=_private_values(target),
    )
    report_path = output_dir / "real-data-ui-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local A6 desktop/iPhone browser QA against a canonical SQLite database."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--conversation-id",
        default=None,
        help=(
            "Optional canonical conversation_id used only locally to choose the QA target. "
            "The identifier is never written to the report."
        ),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/a6-real-data-ui"))
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument(
        "--keep-screenshots",
        action="store_true",
        help="Retain screenshots that may contain private message content. Off by default.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_real_data_ui_qa(
        database=args.database,
        output_dir=args.output,
        timeout_ms=args.timeout_ms,
        keep_screenshots=args.keep_screenshots,
        conversation_id=args.conversation_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
