from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EXPECTED_TABS = [
    "Konverzace",
    "Časová osa",
    "Grafy",
    "Významná období",
    "Lexikální témata",
    "Vybrané zprávy",
    "Analýza",
]


@dataclass(frozen=True)
class ViewportCase:
    name: str
    width: int
    height: int


VIEWPORTS = (
    ViewportCase("desktop", 1440, 900),
    ViewportCase("iphone-portrait", 390, 844),
    ViewportCase("iphone-landscape", 844, 390),
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
          return {
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
            root_scroll_width: root.scrollWidth,
            body_scroll_width: body.scrollWidth,
            content_scroll_width: content ? content.scrollWidth : null,
            page_horizontal_overflow_px: Math.max(root.scrollWidth, body.scrollWidth) - window.innerWidth,
          };
        }
        """
    )


def run_viewport_smoke(*, url: str, output_dir: Path, timeout_ms: int = 30_000) -> dict[str, Any]:
    """Run A6 demo UI smoke checks in Chromium for desktop and iPhone-sized viewports.

    Playwright is imported lazily so normal repository imports/tests do not require
    the browser dependency. This smoke deliberately uses A6 demo data only; no
    real archive or personal content is written to CI artifacts.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised by CI environment setup
        raise RuntimeError("Playwright is required for A6 viewport smoke") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "contract": "a6-browser-viewport-v1",
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

                    # Exercise both ends of the tab strip. This catches mobile
                    # regressions where later tabs exist in DOM but cannot be reached.
                    for tab_name in (EXPECTED_TABS[0], EXPECTED_TABS[-1]):
                        tab = page.get_by_role("tab", name=tab_name, exact=True)
                        tab.scroll_into_view_if_needed(timeout=timeout_ms)
                        tab.click(timeout=timeout_ms)
                        if tab.get_attribute("aria-selected") != "true":
                            errors.append(f"tab_not_selectable={tab_name}")

                    metrics = _page_metrics(page)
                    overflow_px = int(metrics["page_horizontal_overflow_px"] or 0)
                    # Nested dataframes/tab strips may scroll; the page itself must not.
                    if overflow_px > 2:
                        errors.append(f"page_horizontal_overflow_px={overflow_px}")

                    screenshot = output_dir / f"{_safe_name(case.name)}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                except Exception as exc:  # fail closed, preserving screenshot/report when possible
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
    parser = argparse.ArgumentParser(description="A6 Streamlit browser viewport smoke")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=Path("artifacts/a6-viewport-smoke"))
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args(argv)

    report = run_viewport_smoke(url=args.url, output_dir=args.output, timeout_ms=args.timeout_ms)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
