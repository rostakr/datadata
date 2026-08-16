from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import secrets
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

from a6.local_runtime import LOCAL_DATABASE_ENV
from tools.real_archive_gate import run_gate


class LocalAppError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_workdir(
    *,
    home: str | Path | None = None,
    now: datetime | None = None,
    token: str | None = None,
) -> Path:
    """Return a unique private run directory outside the repository by default."""

    base = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    stamp = instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    suffix = token or secrets.token_hex(4)
    return base / ".analyzazprav" / "runs" / f"{stamp}-{suffix}"


def _validate_args(args: argparse.Namespace) -> None:
    database_mode = args.database is not None
    raw_mode = args.chat_db is not None
    if database_mode == raw_mode:
        raise LocalAppError("Provide exactly one of --database or --chat-db.")

    selector_count = int(args.target is not None) + int(args.conversation_id is not None)
    if database_mode:
        if selector_count or args.workdir is not None or args.attachments_root is not None:
            raise LocalAppError(
                "--target, --conversation-id, --workdir and --attachments-root are only valid with --chat-db."
            )
        return

    if selector_count != 1:
        raise LocalAppError(
            "Raw archive mode requires exactly one of --target or --conversation-id."
        )


def _existing_database(path: str | Path) -> Path:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise LocalAppError(f"Canonical SQLite database does not exist: {database}")
    return database


def _database_from_archive(
    args: argparse.Namespace,
    *,
    gate_runner: Callable[..., Mapping[str, Any]] = run_gate,
) -> tuple[Path, str, Mapping[str, Any]]:
    workdir = (
        Path(args.workdir).expanduser().resolve()
        if args.workdir is not None
        else default_workdir()
    )
    report = gate_runner(
        chat_db=args.chat_db,
        workdir=workdir,
        target=args.target,
        conversation_id=args.conversation_id,
        attachments_root=args.attachments_root,
    )
    verdict = str(report.get("verdict") or "INVALID")
    if verdict not in {"VALID", "NEEDS_REVIEW"}:
        raise LocalAppError(
            "Real archive gate returned INVALID; local UI will not start from an unvalidated canonical result."
        )

    database = workdir / "messages.sqlite"
    if not database.is_file():
        raise LocalAppError(
            "Real archive gate did not produce the expected canonical messages.sqlite."
        )
    return database.resolve(), verdict, report


def _streamlit_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(_repo_root() / "app.py"),
        "--server.address=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]


def _require_streamlit() -> None:
    if importlib.util.find_spec("streamlit") is None:
        raise LocalAppError(
            "Streamlit is not installed. Run: python -m pip install -r requirements.txt"
        )


def _launch_ui(
    database: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> int:
    _require_streamlit()
    env = dict(os.environ if environ is None else environ)
    env[LOCAL_DATABASE_ENV] = str(database.resolve())
    completed = runner(
        _streamlit_command(),
        cwd=_repo_root(),
        env=env,
        text=True,
        check=False,
    )
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local Analýza zpráv workflow from canonical SQLite or Apple Messages chat.db."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path, help="Existing canonical messages.sqlite")
    source.add_argument("--chat-db", type=Path, help="Apple Messages chat.db to process read-only")

    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--target", help="Exact canonical/source identity; never fuzzy matched")
    selector.add_argument("--conversation-id", type=int, help="Authoritative canonical conversation ID")

    parser.add_argument("--workdir", type=Path, help="Optional empty/nonexistent private workdir")
    parser.add_argument("--attachments-root", type=Path, help="Optional Apple Messages Attachments root")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_args(args)

    if args.database is not None:
        database = _existing_database(args.database)
        print("Canonical SQLite: ready. Starting local A6 UI.")
        return _launch_ui(database)

    database, verdict, report = _database_from_archive(args)
    counts = report.get("counts") if isinstance(report.get("counts"), Mapping) else {}
    errors = int(counts.get("errors", 0)) if isinstance(counts, Mapping) else 0
    warnings = int(counts.get("warnings", 0)) if isinstance(counts, Mapping) else 0
    print(f"Real archive gate: {verdict} (errors={errors}, warnings={warnings}).")
    if verdict == "NEEDS_REVIEW":
        print("Opening the local UI for review; NEEDS_REVIEW is not equivalent to release-ready VALID.")
    else:
        print("Canonical SQLite validated. Starting local A6 UI.")
    return _launch_ui(database)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except LocalAppError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
