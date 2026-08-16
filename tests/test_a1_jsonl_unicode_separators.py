from __future__ import annotations

import json
from pathlib import Path

from analiza_zprav_a1.importer import import_generic_text


def test_jsonl_escapes_unicode_line_separators_without_changing_message_text(tmp_path: Path) -> None:
    source = tmp_path / "messages.txt"
    expected = "before\u2028middle\u2029after"
    source.write_text(expected, encoding="utf-8")
    output = tmp_path / "out"

    stats = import_generic_text(source, output, "whole")

    raw = (output / "messages.jsonl").read_text(encoding="utf-8")
    assert stats.messages_seen == 1
    assert stats.messages_emitted == 1
    assert raw.count("\n") == 1
    assert "\u2028" not in raw
    assert "\u2029" not in raw
    assert "\\u2028" in raw
    assert "\\u2029" in raw

    parsed = json.loads(raw)
    assert parsed["text"] == expected
