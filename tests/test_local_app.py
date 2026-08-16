from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from a6.local_runtime import LOCAL_DATABASE_ENV, configured_database
from tools import local_app


def _raw_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "database": None,
        "chat_db": tmp_path / "chat.db",
        "target": "EXACT_TARGET",
        "conversation_id": None,
        "workdir": tmp_path / "run",
        "attachments_root": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_default_workdir_is_private_and_unique_under_home(tmp_path: Path):
    when = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)
    workdir = local_app.default_workdir(home=tmp_path, now=when, token="abcd1234")

    assert workdir == tmp_path / ".analyzazprav" / "runs" / "20260816T180000.000000Z-abcd1234"
    assert local_app._repo_root() not in workdir.parents


def test_parser_accepts_existing_database_mode():
    args = local_app.build_parser().parse_args(["--database", "messages.sqlite"])
    local_app._validate_args(args)
    assert args.database == Path("messages.sqlite")


def test_database_mode_rejects_archive_only_options():
    args = local_app.build_parser().parse_args(
        ["--database", "messages.sqlite", "--target", "EXACT_TARGET"]
    )
    with pytest.raises(local_app.LocalAppError, match="only valid with --chat-db"):
        local_app._validate_args(args)


def test_raw_mode_requires_exactly_one_selector():
    args = local_app.build_parser().parse_args(["--chat-db", "chat.db"])
    with pytest.raises(local_app.LocalAppError, match="exactly one"):
        local_app._validate_args(args)


def test_configured_database_runtime_contract_resolves_path(tmp_path: Path):
    database = tmp_path / "messages.sqlite"
    assert configured_database({}) is None
    assert configured_database({LOCAL_DATABASE_ENV: str(database)}) == database.resolve()


def test_invalid_gate_fails_closed_before_ui(tmp_path: Path):
    args = _raw_args(tmp_path)

    def invalid_gate(**kwargs):
        return {"verdict": "INVALID", "counts": {"errors": 1, "warnings": 0}}

    with pytest.raises(local_app.LocalAppError, match="will not start"):
        local_app._database_from_archive(args, gate_runner=invalid_gate)


def test_needs_review_gate_produces_local_database_without_dumping_report(tmp_path: Path):
    args = _raw_args(tmp_path)
    private_report = {
        "verdict": "NEEDS_REVIEW",
        "counts": {"errors": 0, "warnings": 2},
        "private_inventory": {"participant": "PRIVATE VALUE"},
    }

    def needs_review_gate(**kwargs):
        workdir = Path(kwargs["workdir"])
        workdir.mkdir(parents=True)
        (workdir / "messages.sqlite").touch()
        return private_report

    database, verdict, report = local_app._database_from_archive(
        args,
        gate_runner=needs_review_gate,
    )
    assert database == (tmp_path / "run" / "messages.sqlite").resolve()
    assert verdict == "NEEDS_REVIEW"
    assert report is private_report


def test_needs_review_console_prints_summary_not_private_report(monkeypatch, tmp_path: Path, capsys):
    database = tmp_path / "messages.sqlite"
    database.touch()
    private_report = {
        "verdict": "NEEDS_REVIEW",
        "counts": {"errors": 0, "warnings": 2},
        "private_inventory": {"participant": "PRIVATE VALUE"},
    }

    monkeypatch.setattr(
        local_app,
        "_database_from_archive",
        lambda args: (database, "NEEDS_REVIEW", private_report),
    )
    monkeypatch.setattr(local_app, "_launch_ui", lambda selected: 0)

    code = local_app.run(
        ["--chat-db", str(tmp_path / "chat.db"), "--target", "EXACT_TARGET"]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "NEEDS_REVIEW" in output
    assert "errors=0" in output
    assert "warnings=2" in output
    assert "PRIVATE VALUE" not in output
    assert "private_inventory" not in output


def test_launch_ui_sets_database_env_and_uses_module_streamlit(tmp_path: Path, monkeypatch):
    database = tmp_path / "messages.sqlite"
    database.touch()
    captured = {}

    monkeypatch.setattr(local_app, "_require_streamlit", lambda: None)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    code = local_app._launch_ui(
        database,
        runner=fake_run,
        environ={"KEEP": "1"},
    )

    assert code == 0
    assert captured["command"][:4] == [
        local_app.sys.executable,
        "-m",
        "streamlit",
        "run",
    ]
    assert captured["command"][4] == str(local_app._repo_root() / "app.py")
    assert captured["env"][LOCAL_DATABASE_ENV] == str(database.resolve())
    assert captured["env"]["KEEP"] == "1"
    assert captured["cwd"] == local_app._repo_root()
    assert captured["check"] is False


def test_run_does_not_launch_when_archive_resolution_fails(monkeypatch, tmp_path: Path):
    launched = []

    def fail_archive(_args):
        raise local_app.LocalAppError("gate blocked")

    monkeypatch.setattr(local_app, "_database_from_archive", fail_archive)
    monkeypatch.setattr(local_app, "_launch_ui", lambda database: launched.append(database) or 0)

    with pytest.raises(local_app.LocalAppError, match="gate blocked"):
        local_app.run(["--chat-db", str(tmp_path / "chat.db"), "--target", "EXACT_TARGET"])
    assert launched == []
