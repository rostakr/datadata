from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

from tools.a6_viewport_smoke import EXPECTED_TABS, VIEWPORTS, _page_metrics


REAL_DATA_REQUIRED_TABS = ("Konverzace", "Vybrané zprávy", "Analýza")


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


def _select_sqlite_source(page: Any, database: Path, timeout_ms: int) -> None:
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


def run_real_data_ui_qa(
    *,
    database: Path,
    output_dir: Path,
    timeout_ms: int = 30_000,
    keep_screenshots: bool = False,
) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Canonical SQLite database does not exist: {database}")

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
        "contract": "a6-real-data-browser-v1",
        "database": _database_label(database),
        "expected_tabs": EXPECTED_TABS,
        "required_interaction_tabs": list(REAL_DATA_REQUIRED_TABS),
        "screenshots_retained": bool(keep_screenshots),
        "cases": [],
        "status": "PASS",
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
                    browser_errors: list[str] = []
                    page.on("pageerror", lambda exc, bucket=browser_errors: bucket.append(str(exc)))
                    screenshot_name: str | None = None
                    metrics: dict[str, Any] = {}
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                        page.get_by_role("heading", name="Analýza zpráv", exact=True).wait_for(
                            state="visible", timeout=timeout_ms
                        )
                        _select_sqlite_source(page, database, timeout_ms)

                        exception_count = page.locator('[data-testid="stException"]').count()
                        if exception_count:
                            errors.append(f"streamlit_exception_count={exception_count}")

                        tabs = page.get_by_role("tab")
                        tab_labels = [label.strip() for label in tabs.all_inner_texts()]
                        if tab_labels != EXPECTED_TABS:
                            errors.append("tab_labels_mismatch=" + json.dumps(tab_labels, ensure_ascii=False))

                        for tab_name in REAL_DATA_REQUIRED_TABS:
                            tab = page.get_by_role("tab", name=tab_name, exact=True)
                            tab.scroll_into_view_if_needed(timeout=timeout_ms)
                            tab.click(timeout=timeout_ms)
                            if tab.get_attribute("aria-selected") != "true":
                                errors.append(f"tab_not_selectable={tab_name}")

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
                        errors.append(f"browser_check_error={type(exc).__name__}: {exc}")
                        if keep_screenshots:
                            screenshot = output_dir / f"{case.name}-failure.png"
                            try:
                                page.screenshot(path=str(screenshot), full_page=True)
                                screenshot_name = screenshot.name
                            except Exception:
                                screenshot_name = None
                    finally:
                        context.close()

                    if browser_errors:
                        errors.extend(f"pageerror={value}" for value in browser_errors)
                    case_report = {
                        "name": case.name,
                        "width": case.width,
                        "height": case.height,
                        "max_metrics_per_row": case.max_metrics_per_row,
                        "metrics": metrics,
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

    report_path = output_dir / "real-data-ui-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local A6 desktop/iPhone browser QA against a canonical SQLite database."
    )
    parser.add_argument("--database", required=True, type=Path)
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
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
