from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app


def test_source_without_launcher_database_preserves_original_selector(monkeypatch):
    expected = ("messages", "info", "findings", None)
    monkeypatch.setattr(app, "configured_database", lambda: None)
    monkeypatch.setattr(app, "_ORIGINAL_SOURCE", lambda: expected)

    assert app.source() == expected
    assert app._CURRENT_DB_PATH is None


def test_source_with_launcher_database_bypasses_manual_selector(monkeypatch, tmp_path: Path):
    database = (tmp_path / "messages.sqlite").resolve()
    calls: list[str] = []

    class Sidebar:
        def header(self, value):
            calls.append(f"header:{value}")

        def caption(self, value):
            calls.append(f"caption:{value}")

        def error(self, value):
            calls.append(f"error:{value}")

    monkeypatch.setattr(app, "configured_database", lambda: database)
    monkeypatch.setattr(
        app,
        "_ORIGINAL_SOURCE",
        lambda: (_ for _ in ()).throw(AssertionError("manual selector must not run")),
    )
    monkeypatch.setattr(
        app._legacy,
        "load_db",
        lambda path: ("messages", "info", "findings") if path == str(database) else None,
    )
    monkeypatch.setattr(
        app._legacy,
        "st",
        SimpleNamespace(sidebar=Sidebar(), stop=lambda: (_ for _ in ()).throw(RuntimeError("stop"))),
    )

    result = app.source()

    assert result == ("messages", "info", "findings", str(database))
    assert app._CURRENT_DB_PATH == str(database)
    assert calls == [
        "header:Zdroj dat",
        "caption:Režim: canonical SQLite (lokální launcher)",
    ]
