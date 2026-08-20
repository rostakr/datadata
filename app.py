from __future__ import annotations

"""Runtime v2 Streamlit entrypoint.

The historical A6 UI remains in ``a6.app_legacy`` only as migration/reference
code. The production entrypoint uses the simplified canonical -> signals ->
evidence packs -> interpreter flow from ``a6.runtime_ui``.
"""

from a6.runtime_ui import main


if __name__ == "__main__":
    main()
