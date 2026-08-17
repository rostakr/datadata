from __future__ import annotations

"""Private/local A6 QA entrypoint with deterministic canonical target selection.

The target is provided only through the child-process environment. It is never
persisted by this module and is not written to QA reports.
"""

import os
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import app as _app  # noqa: E402
from a6 import app_legacy as _legacy  # noqa: E402

LOCAL_CONVERSATION_ENV = "ANALYZA_ZPRAV_CONVERSATION_ID"
_ORIGINAL_SELECT_CONVERSATION = _legacy.select_conversation


def _targeted_select_conversation(frame):
    raw = str(os.environ.get(LOCAL_CONVERSATION_ENV, "")).strip()
    if not raw:
        return _ORIGINAL_SELECT_CONVERSATION(frame)

    scoped = frame[frame["conversation_id"].astype(str) == raw].reset_index(drop=True)
    if scoped.empty:
        _legacy.st.error("Launcher-provided canonical conversation is not present in the configured database.")
        _legacy.st.stop()
    return _ORIGINAL_SELECT_CONVERSATION(scoped)


_legacy.select_conversation = _targeted_select_conversation


if __name__ == "__main__":
    _app.main()
