from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


LOCAL_DATABASE_ENV = "ANALYZA_ZPRAV_DB"


def configured_database(environ: Mapping[str, str] | None = None) -> Path | None:
    """Return the launcher-provided canonical SQLite path, if configured.

    The value is intentionally process-local. It is never persisted by A6 and
    does not change the normal interactive source selector when absent.
    """

    source = os.environ if environ is None else environ
    raw = str(source.get(LOCAL_DATABASE_ENV, "")).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()
