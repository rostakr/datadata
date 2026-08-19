from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from .interpreter import PROMPT_VERSION
from .models import EvidencePack


STORE_SCHEMA_VERSION = 1


def default_store_path() -> Path:
    configured = str(os.environ.get("ANALYZA_ZPRAV_RUNTIME_STORE", "")).strip()
    path = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".datadata" / "cache" / "runtime-v2.sqlite"
    )
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def result_fingerprint(
    packs: Sequence[EvidencePack],
    *,
    provider: str,
    model: str,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Hash provider-visible content plus the private local evidence mapping.

    The local mapping is part of the fingerprint so identical text belonging to
    different canonical messages cannot reuse a materialized result. The hashed
    material is never sent to the provider or emitted in public reports.
    """

    canonical = {
        "schema": STORE_SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "packs": [
            {
                "provider_payload": pack.provider_payload(),
                "local_evidence": [
                    {
                        "label": item.label,
                        "message_id": item.message_id,
                        "membership_id": item.membership_id,
                        "conversation_id": item.conversation_id,
                        "source_record_keys": list(item.source_record_keys),
                        "source_snapshot_keys": list(item.source_snapshot_keys),
                        "source_parser_versions": list(item.source_parser_versions),
                    }
                    for item in pack.items
                ],
            }
            for pack in packs
        ],
    }
    raw = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()


class AnalysisStore:
    """Small private SQLite cache for validated Runtime v2 results."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_results (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM runtime_results WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            try:
                value = json.loads(str(row[0]))
            except json.JSONDecodeError:
                conn.execute("DELETE FROM runtime_results WHERE cache_key=?", (cache_key,))
                return None
            if not isinstance(value, dict):
                conn.execute("DELETE FROM runtime_results WHERE cache_key=?", (cache_key,))
                return None
            return value

    def put(
        self,
        cache_key: str,
        result: Mapping[str, Any],
        *,
        provider: str,
        model: str,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        payload = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_results(cache_key, provider, model, prompt_version, result_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    prompt_version=excluded.prompt_version,
                    result_json=excluded.result_json,
                    created_at=CURRENT_TIMESTAMP
                """,
                (cache_key, provider, model, prompt_version, payload),
            )
