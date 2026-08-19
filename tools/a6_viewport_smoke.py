from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EXPECTED_TABS = [
    "Konverzace",
    "Signály",
    "Interpretace",
]


@dataclass(frozen=True)
class ViewportCase:
    name: str
    width: int
    height: int
    max_metrics_per_row: int


VIEWPORTS = (
    ViewportCase("desktop", 1440, 900, 6),
    ViewportCase("iphone-portrait", 390, 844, 1),
    ViewportCase("iphone-landscape", 844, 390, 2),
)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)


def _page_metrics(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const root = document.documentElement;
          const body = document.body;
          const streamlit = document.querySelector('[data-testid="stAppViewContainer"]');
          const content = streamlit || body;
          const metricNodes = Array.from(document.querySelectorAll('[data-testid="stMetric"]')).slice(0, 6);
          const metricBoxes = metricNodes.map((node) => {
            const rect = node.getBoundingClientRect();
            return {left: rect.left, top: rect.top, width: rect.width, height: rect.height};
          });
          const rowCounts = [];
          for (const box of metricBoxes) {
            let row = rowCounts.find((item) => Math.abs(item.top - box.top) <= 4);
            if (!row) {
              row = {top: box.top, count: 0};
              rowCounts.push(row);
            }
            row.count += 1;
          }
          return {
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
            root_scroll_width: root.scrollWidth,
            body_scroll_width: body.scrollWidth,
            content_scroll_width: content ? content.scrollWidth : null,
            page_horizontal_overflow_px: Math.max(root.scrollWidth, body.scrollWidth) - window.innerWidth,
            metric_count: metricBoxes.length,
            metric_row_counts: rowCounts.map((item) => item.count),
            max_metrics_same_row: rowCounts.length ? Math.max(...rowCounts.map((item) => item.count)) : 0,
          };
        }
        """
    )


def run_viewport_smoke(*, url: str, output_dir: Path, timeout_ms: int = 30_000) -> dict[str, Any]:
    """Run Runtime v2 demo UI smoke checks in Chromium."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised by CI environment setup
        raise RuntimeError("Playwright is required for A6 viewport smoke") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "contract": "runtime-v2-browser-viewport-v1",
        "url": url,
        "expected_tabs": EXPECTED_TABS,
        "cases": [],
        "status": "PASS",
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for case in VIEWPORTS:
                context = browser.new_context(viewport={"width": case.width, "height": case.height})
                page = context.new_page()
                errors: list[str] = []
                browser_errors: list[str] = []
                page.on("pageerror", lambda exc, bucket=browser_errors: bucket.append(str(exc)))

                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    page.get_by_role("heading", name="Analýza zpráv", exact=True).wait_for(
                        state="visible", timeout=timeout_ms
                    )

                    exception_count = page.locator('[data-testid="stException"]').count()
                    if exception_count:
                        errors.append(f"streamlit_exception_count={exception_count}")

                    tab_list = page.get_by_role("tablist")
                    tab_list.wait_for(state="visible", timeout=timeout_ms)
                    tabs = page.get_by_role("tab")
                    tab_labels = [label.strip() for label in tabs.all_inner_texts()]
                    if tab_labels != EXPECTED_TABS:
                        errors.append(
                            "tab_labels_mismatch=" + json.dumps(tab_labels, ensure_ascii=False)
                        )

                    for tab_name in (EXPECTED_TABS[0], EXPECTED_TABS[-1]):
                        tab = page.get_by_role("tab", name=tab_name, exact=True)
                        tab.scroll_into_view_if_needed(timeout=timeout_ms)
                        tab.click(timeout=timeout_ms)
                        if tab.get_attribute("aria-selected") != "true":
                            errors.append(f"tab_not_selectable={tab_name}")

                    metrics = _page_metrics(page)
                    overflow_px = int(metrics["page_horizontal_overflow_px"] or 0)
                    if overflow_px > 2:
                        errors.append(f"page_horizontal_overflow_px={overflow_px}")

                    metric_count = int(metrics["metric_count"] or 0)
                    if metric_count != 6:
                        errors.append(f"metric_count={metric_count}, expected=6")
                    max_same_row = int(metrics["max_metrics_same_row"] or 0)
                    if max_same_row > case.max_metrics_per_row:
                        errors.append(
                            f"max_metrics_same_row={max_same_row}, allowed={case.max_metrics_per_row}"
                        )

                    screenshot = output_dir / f"{_safe_name(case.name)}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                except Exception as exc:
                    errors.append(f"browser_check_error={type(exc).__name__}: {exc}")
                    metrics = {}
                    screenshot = output_dir / f"{_safe_name(case.name)}-failure.png"
                    try:
                        page.screenshot(path=str(screenshot), full_page=True)
                    except Exception:
                        screenshot = None
                finally:
                    context.close()

                if browser_errors:
                    errors.extend(f"pageerror={value}" for value in browser_errors)

                case_report = {
                    **asdict(case),
                    "metrics": metrics,
                    "errors": errors,
                    "status": "PASS" if not errors else "FAIL",
                    "screenshot": None if screenshot is None else screenshot.name,
                }
                report["cases"].append(case_report)
                if errors:
                    report["status"] = "FAIL"
        finally:
            browser.close()

    report_path = output_dir / "viewport-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime v2 Streamlit browser viewport smoke")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=Path("artifacts/a6-viewport-smoke"))
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args(argv)

    report = run_viewport_smoke(url=args.url, output_dir=args.output, timeout_ms=args.timeout_ms)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
