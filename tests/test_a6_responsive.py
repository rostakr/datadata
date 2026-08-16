from __future__ import annotations

from a6.responsive import (
    MIN_TOUCH_TARGET_PX,
    PHONE_BREAKPOINT_PX,
    TABLET_BREAKPOINT_PX,
    install_responsive_contract,
    responsive_css,
)


def test_responsive_css_preserves_all_content_and_mobile_navigation():
    css = responsive_css()

    assert f"@media (max-width: {TABLET_BREAKPOINT_PX}px)" in css
    assert f"@media (max-width: {PHONE_BREAKPOINT_PX}px)" in css
    assert f"min-height: {MIN_TOUCH_TARGET_PX}px" in css
    assert '[data-baseweb="tab-list"]' in css
    assert "overflow-x: auto" in css
    assert '[data-testid="stDataFrame"]' in css
    assert '[data-testid="stHorizontalBlock"]' in css
    assert "flex-wrap: wrap" in css
    assert "flex-basis: 100%" in css
    assert "display: none" not in css.lower()


def test_responsive_contract_is_injected_as_css_only():
    calls = []

    class FakeStreamlit:
        @staticmethod
        def markdown(body, **kwargs):
            calls.append((body, kwargs))

    install_responsive_contract(FakeStreamlit)

    assert len(calls) == 1
    body, kwargs = calls[0]
    assert body.startswith("<style>")
    assert body.endswith("</style>")
    assert kwargs == {"unsafe_allow_html": True}
