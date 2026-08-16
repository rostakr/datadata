from __future__ import annotations

from pathlib import Path

from analyzazprav.normalization.database import CanonicalDatabase


def test_message_source_current_import_lookup_has_composite_index(tmp_path: Path) -> None:
    db = CanonicalDatabase(tmp_path / "messages.sqlite")
    db.initialize()
    try:
        indexes = {
            row[1]: row
            for row in db.conn.execute("PRAGMA index_list('message_source')").fetchall()
        }
        assert "idx_message_source_import_record_key" in indexes
        columns = [
            row[2]
            for row in db.conn.execute(
                "PRAGMA index_info('idx_message_source_import_record_key')"
            ).fetchall()
        ]
        assert columns == ["import_run_id", "source_record_key"]
    finally:
        db.close()
