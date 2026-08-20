from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from a6 import runtime_ui
from a6.data import SourceInfo, demo_messages


def test_source_without_launcher_database_preserves_interactive_demo_selector(monkeypatch):
    class Sidebar:
        def header(self, value):
            assert value == "Zdroj dat"

        def radio(self, label, options, horizontal=False):
            assert label == "Režim"
            assert options == ["Demo", "SQLite"]
            assert horizontal is True
            return "Demo"

    monkeypatch.setattr(runtime_ui, "configured_database", lambda: None)
    monkeypatch.setattr(runtime_ui, "st", SimpleNamespace(sidebar=Sidebar()))

    messages, info, findings, db_path = runtime_ui._source()

    assert len(messages) == len(demo_messages())
    assert info == SourceInfo("demo", "Vestavěná demo data")
    assert findings.empty
    assert db_path is None


def test_source_with_launcher_database_bypasses_manual_selector(monkeypatch, tmp_path: Path):
    database = (tmp_path / "messages.sqlite").resolve()
    expected = ("messages", "info", "findings")
    calls: list[str] = []

    monkeypatch.setattr(runtime_ui, "configured_database", lambda: database)

    def fake_load_db(path):
        calls.append(path)
        assert path == str(database)
        return expected

    monkeypatch.setattr(runtime_ui, "_load_db", fake_load_db)
    monkeypatch.setattr(
        runtime_ui,
        "st",
        SimpleNamespace(
            sidebar=SimpleNamespace(
                header=lambda *_: (_ for _ in ()).throw(
                    AssertionError("interactive source selector must not run")
                )
            ),
            error=lambda value: (_ for _ in ()).throw(AssertionError(value)),
            stop=lambda: (_ for _ in ()).throw(RuntimeError("stop")),
        ),
    )

    result = runtime_ui._source()

    assert result == ("messages", "info", "findings", str(database))
    assert calls == [str(database)]
