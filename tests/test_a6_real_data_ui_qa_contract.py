from __future__ import annotations

from pathlib import Path

from tools.a6_real_data_ui_qa import (
    REAL_DATA_REQUIRED_TABS,
    _database_label,
    build_parser,
)


def test_real_data_report_redacts_absolute_database_path():
    assert _database_label(Path('/Users/example/private/messages.sqlite')) == 'messages.sqlite'


def test_real_data_browser_qa_exercises_evidence_flow_tabs():
    assert REAL_DATA_REQUIRED_TABS == ('Konverzace', 'Vybrané zprávy', 'Analýza')


def test_real_data_screenshots_are_opt_in():
    parser = build_parser()
    args = parser.parse_args(['--database', 'messages.sqlite'])
    assert args.keep_screenshots is False

    opted_in = parser.parse_args(['--database', 'messages.sqlite', '--keep-screenshots'])
    assert opted_in.keep_screenshots is True
