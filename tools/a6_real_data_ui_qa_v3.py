from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from tools.a6_real_data_ui_qa import (
    REAL_DATA_REQUIRED_TABS,
    _assert_report_privacy,
    _build_data_checks,
    _database_label,
    _free_port,
    _private_values,
    _select_target_context,
    _wait_for_health,
)
from tools.a6_viewport_smoke import EXPECTED_TABS, VIEWPORTS, _page_metrics

_LOCAL_DATABASE_ENV = "ANALYZA_ZPRAV_DB"
_LOCAL_CONVERSATION_ENV = "ANALYZA_ZPRAV_CONVERSATION_ID"


def _empty_interaction_checks() -> dict[str, bool]:
    return {
        "period_control": False,
        "conversation_messages": False,
        "a4_metrics": False,
        "finding_evidence": False,
        "selected_evidence": False,
        "analysis_packet": False,
    }


def _active_tabpanel(page: Any) -> Any:
    """Return the currently visible Streamlit tab panel.

    Streamlit keeps multiple tab bodies in the DOM, so global text locators can
    legitimately match content in more than one tab and trigger Playwright
    strict-mode errors. Acceptance checks are therefore scoped to the visible
    tab panel.
    """

    return page.locator('[role="tabpanel"]:visible').first


def _select_finding_in_ui_v3(
    page: Any,
    target: Any,
    timeout_ms: int,
    stage_ref: dict[str, str],
) -> None:
    """Select the deterministic A4 finding without relying on pointer hit testing."""

    panel = _active_tabpanel(page)
    stage_ref["value"] = "finding_select_wait"
    combobox = panel.get_by_role("combobox", name="Analytický nález", exact=True)
    combobox.wait_for(state="visible", timeout=timeout_ms)

    # React-Aria/Streamlit selectbox wrappers can intercept pointer events at
    # narrow viewports. Keyboard activation avoids that presentation-layer
    # hit-testing problem while still exercising the real interactive widget.
    stage_ref["value"] = "finding_select_open"
    combobox.focus()
    combobox.press("ArrowDown")

    stage_ref["value"] = "finding_select_option"
    option = page.get_by_role("option", name=target.finding_option_label, exact=True)
    option.wait_for(state="visible", timeout=timeout_ms)
    option.click(timeout=timeout_ms, force=True)
    page.wait_for_timeout(900)


def _exercise_real_interactions_v3(
    page: Any,
    target: Any,
    timeout_ms: int,
    stage_ref: dict[str, str],
    checks: dict[str, bool],
) -> dict[str, bool]:
    """Exercise the real A6 flow while exposing only privacy-safe stage names."""

    stage_ref["value"] = "period_control"
    # The backend data check separately proves that period filtering narrows the
    # canonical membership set. Browser acceptance only needs to prove that the
    # real Streamlit date-input widget is rendered; its label may be represented
    # by Streamlit/React-Aria markup rather than a standalone text node.
    period_control = page.locator('[data-testid="stDateInput"]').first
    period_control.wait_for(state="visible", timeout=timeout_ms)
    checks["period_control"] = True

    # Konverzace is the default active tab. Do not perform a redundant click on
    # the already-selected tab; verify its real rendered content instead.
    stage_ref["value"] = "conversation_content"
    panel = _active_tabpanel(page)
    panel.get_by_text("Vybrat zprávy pro analýzu", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    panel.get_by_text("membership_id:", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["conversation_messages"] = True

    stage_ref["value"] = "graphs_tab_click"
    page.get_by_role("tab", name="Grafy", exact=True).click(timeout=timeout_ms)
    stage_ref["value"] = "graphs_content"
    panel = _active_tabpanel(page)
    panel.get_by_text("Zdroj metrik: A4 latest-run views", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["a4_metrics"] = True

    stage_ref["value"] = "significant_periods_tab_click"
    page.get_by_role("tab", name="Významná období", exact=True).click(timeout=timeout_ms)
    stage_ref["value"] = "finding_select"
    _select_finding_in_ui_v3(page, target, timeout_ms, stage_ref)
    stage_ref["value"] = "finding_provenance"
    panel = _active_tabpanel(page)
    panel.get_by_text("Message source provenance", exact=True).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    stage_ref["value"] = "finding_evidence_button"
    button = panel.get_by_role(
        "button",
        name="Použít evidence tohoto nálezu pro AI analýzu",
        exact=True,
    )
    button.wait_for(state="visible", timeout=timeout_ms)
    checks["finding_evidence"] = True
    button.click(timeout=timeout_ms)
    page.wait_for_timeout(900)

    stage_ref["value"] = "selected_messages_tab_click"
    page.get_by_role("tab", name="Vybrané zprávy", exact=True).click(timeout=timeout_ms)
    stage_ref["value"] = "selected_messages_content"
    panel = _active_tabpanel(page)
    panel.get_by_text("Aktivní zdroj výběru: A4 nález", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    panel.get_by_text("Message source provenance", exact=True).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["selected_evidence"] = True

    stage_ref["value"] = "analysis_tab_click"
    page.get_by_role("tab", name="Analýza", exact=True).click(timeout=timeout_ms)
    stage_ref["value"] = "analysis_content"
    panel = _active_tabpanel(page)
    panel.get_by_text("Aktivní zdroj výběru: A4 nález", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    panel.get_by_text("A6 neposílá celý archiv do AI.", exact=False).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    panel.get_by_text("Lokální AI analýza", exact=True).wait_for(
        state="visible", timeout=timeout_ms
    )
    checks["analysis_packet"] = True
    stage_ref["value"] = "complete"
    return checks


def run_real_data_ui_qa_v3(
    *,
    database: Path,
    output_dir: Path,
    timeout_ms: int = 30_000,
    keep_screenshots: bool = False,
    conversation_id: str | None = None,
    browser_channel: str | None = None,
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
    app_path = Path(__file__).resolve().with_name("a6_real_data_target_app.py")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    child_env = dict(os.environ)
    child_env[_LOCAL_DATABASE_ENV] = str(database)
    child_env[_LOCAL_CONVERSATION_ENV] = target.conversation_id
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    report: dict[str, Any] = {
        "contract": "a6-real-data-browser-v3",
        "database": _database_label(database),
        "expected_tabs": EXPECTED_TABS,
        "required_interaction_tabs": list(REAL_DATA_REQUIRED_TABS),
        "screenshots_retained": bool(keep_screenshots),
        "browser_channel": browser_channel or "bundled-chromium",
        "data_checks": data_checks,
        "cases": [],
        "status": "PASS" if data_checks["status"] == "PASS" else "FAIL",
    }

    try:
        _wait_for_health(health_url, timeout_seconds=max(10.0, timeout_ms / 1000))
        with sync_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": True}
            if browser_channel:
                launch_options["channel"] = browser_channel
            browser = playwright.chromium.launch(**launch_options)
            try:
                for case in VIEWPORTS:
                    context = browser.new_context(viewport={"width": case.width, "height": case.height})
                    page = context.new_page()
                    errors: list[str] = []
                    page_errors: list[str] = []
                    page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(type(exc).__name__))
                    screenshot_name: str | None = None
                    metrics: dict[str, Any] = {}
                    interaction_checks = _empty_interaction_checks()
                    interaction_stage = {"value": "not_started"}
                    failure_stage = "navigate"
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout_ms)

                        failure_stage = "heading"
                        page.get_by_role("heading", name="Analýza zpráv", exact=True).wait_for(
                            state="visible", timeout=timeout_ms
                        )

                        # Streamlit renders Markdown backticks as a <code> element, so
                        # literal backticks are not present in the browser text tree.
                        # The local target app has already fail-closed scoped the frame,
                        # therefore this stable label is sufficient and does not expose
                        # the private canonical identifier in the report.
                        failure_stage = "target_marker"
                        page.get_by_text("conversation_id:", exact=False).first.wait_for(
                            state="visible", timeout=timeout_ms
                        )

                        failure_stage = "streamlit_exception_check"
                        exception_count = page.locator('[data-testid="stException"]').count()
                        if exception_count:
                            errors.append(f"streamlit_exception_count={exception_count}")

                        failure_stage = "tab_contract"
                        tabs = page.get_by_role("tab")
                        tab_labels = [label.strip() for label in tabs.all_inner_texts()]
                        if tab_labels != EXPECTED_TABS:
                            errors.append("tab_labels_mismatch")

                        failure_stage = "real_interactions"
                        _exercise_real_interactions_v3(
                            page,
                            target,
                            timeout_ms,
                            interaction_stage,
                            interaction_checks,
                        )
                        for name, passed in interaction_checks.items():
                            if not passed:
                                errors.append(f"interaction_failed={name}")

                        failure_stage = "responsive_metrics"
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

                        failure_stage = "screenshot"
                        if keep_screenshots:
                            screenshot = output_dir / f"{case.name}.png"
                            page.screenshot(path=str(screenshot), full_page=True)
                            screenshot_name = screenshot.name
                        failure_stage = "complete"
                    except Exception as exc:
                        stage = failure_stage
                        if failure_stage == "real_interactions":
                            stage = f"real_interactions.{interaction_stage['value']}"
                        errors.append(
                            f"browser_check_error={type(exc).__name__};stage={stage}"
                        )
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
                        "interaction_stage": interaction_stage["value"],
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
        description="Run deterministic local A6 desktop/iPhone browser QA against canonical SQLite."
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
    parser.add_argument("--output", type=Path, default=Path("artifacts/a6-real-data-ui-v3"))
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument(
        "--browser-channel",
        default=None,
        help="Optional Playwright Chromium channel such as 'chrome'; default uses bundled Chromium.",
    )
    parser.add_argument(
        "--keep-screenshots",
        action="store_true",
        help="Retain screenshots that may contain private message content. Off by default.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_real_data_ui_qa_v3(
        database=args.database,
        output_dir=args.output,
        timeout_ms=args.timeout_ms,
        keep_screenshots=args.keep_screenshots,
        conversation_id=args.conversation_id,
        browser_channel=args.browser_channel,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
