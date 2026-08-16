from __future__ import annotations

"""Small, explicit responsive contract for the A6 Streamlit UI.

A6 is intentionally local-first and keeps the mature Streamlit read model.  The
CSS below only changes presentation at narrow viewport widths; it does not hide,
truncate, reorder or reinterpret canonical/analytical data.
"""

from typing import Any

TABLET_BREAKPOINT_PX = 768
PHONE_BREAKPOINT_PX = 480
MIN_TOUCH_TARGET_PX = 44


def responsive_css() -> str:
    """Return the versioned A6 responsive presentation contract.

    Stable Streamlit ``data-testid`` attributes are preferred over generated CSS
    class names.  Tabs remain horizontally scrollable instead of being hidden,
    dataframes preserve horizontal scrolling, and metric/column blocks wrap on
    narrow screens so six desktop metrics do not become six unreadable columns.
    """

    return f"""
<style>
@media (max-width: {TABLET_BREAKPOINT_PX}px) {{
  .block-container {{
    padding-left: 1rem;
    padding-right: 1rem;
    padding-top: 1.25rem;
  }}

  [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap;
    gap: 0.5rem;
  }}

  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    min-width: 13rem;
    flex: 1 1 calc(50% - 0.5rem);
  }}

  [data-baseweb="tab-list"] {{
    overflow-x: auto;
    overflow-y: hidden;
    flex-wrap: nowrap;
    scrollbar-width: thin;
    -webkit-overflow-scrolling: touch;
  }}

  [data-baseweb="tab"] {{
    flex: 0 0 auto;
    min-height: {MIN_TOUCH_TARGET_PX}px;
  }}

  [data-testid="stDataFrame"],
  [data-testid="stTable"] {{
    max-width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }}

  [data-testid="stButton"] button,
  [data-testid="stDownloadButton"] button,
  [data-baseweb="select"] > div,
  input,
  textarea {{
    min-height: {MIN_TOUCH_TARGET_PX}px;
  }}

  [data-testid="stMetric"] {{
    min-width: 0;
  }}

  [data-testid="stMetricValue"] {{
    overflow-wrap: anywhere;
  }}
}}

@media (max-width: {PHONE_BREAKPOINT_PX}px) {{
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    min-width: 100%;
    flex-basis: 100%;
  }}

  [data-testid="stButton"] button,
  [data-testid="stDownloadButton"] button {{
    width: 100%;
  }}

  .block-container {{
    padding-left: 0.75rem;
    padding-right: 0.75rem;
  }}
}}
</style>
""".strip()


def install_responsive_contract(st_module: Any) -> None:
    """Inject responsive-only presentation rules into the active Streamlit page."""

    st_module.markdown(responsive_css(), unsafe_allow_html=True)
