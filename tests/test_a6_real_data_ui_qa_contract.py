from __future__ import annotations

from pathlib import Path

import pytest

from a6.evidence import FAIL, STALE, reconcile_a5_evidence_ref
from tools.a6_real_data_ui_qa import (
    REAL_DATA_REQUIRED_TABS,
    SEMANTIC_UI_MARKERS,
    _assert_report_privacy,
    _database_label,
    build_parser,
)


def test_real_data_report_redacts_absolute_database_path():
    assert _database_label(Path('/Users/example/private/messages.sqlite')) == 'messages.sqlite'


def test_real_data_browser_qa_exercises_full_interaction_flow():
    assert REAL_DATA_REQUIRED_TABS == (
        'Konverzace',
        'Grafy',
        'Významná období',
        'Vybrané zprávy',
        'Analýza',
    )


def test_real_data_semantic_separation_contract_is_explicit():
    assert '#### Pozorování' in SEMANTIC_UI_MARKERS
    assert '#### Interpretace' in SEMANTIC_UI_MARKERS
    assert '#### Vzorce' in SEMANTIC_UI_MARKERS
    assert 'Deterministická metric evidence' in SEMANTIC_UI_MARKERS
    assert '#### Nejistoty / chybějící informace' in SEMANTIC_UI_MARKERS


def test_real_data_screenshots_are_opt_in_and_conversation_id_is_local_only():
    parser = build_parser()
    args = parser.parse_args(['--database', 'messages.sqlite'])
    assert args.keep_screenshots is False
    assert args.conversation_id is None

    opted_in = parser.parse_args([
        '--database', 'messages.sqlite',
        '--conversation-id', '16',
        '--keep-screenshots',
    ])
    assert opted_in.keep_screenshots is True
    assert opted_in.conversation_id == '16'


def test_report_privacy_guard_rejects_private_values_and_identifier_keys(tmp_path):
    database = tmp_path / 'private' / 'messages.sqlite'
    database.parent.mkdir()
    database.touch()

    safe = {
        'contract': 'a6-real-data-browser-v2',
        'database': 'messages.sqlite',
        'data_checks': {'canonical_messages': 10, 'status': 'PASS'},
        'cases': [],
        'status': 'PASS',
    }
    _assert_report_privacy(
        safe,
        database=database,
        private_values=('PRIVATE CONTACT NAME', 'PRIVATE MESSAGE CONTENT'),
    )

    leaked_value = dict(safe, note='PRIVATE CONTACT NAME')
    with pytest.raises(RuntimeError, match='private data leaked'):
        _assert_report_privacy(
            leaked_value,
            database=database,
            private_values=('PRIVATE CONTACT NAME',),
        )

    leaked_identifier = dict(safe, conversation_id='16')
    with pytest.raises(RuntimeError, match='forbidden report key'):
        _assert_report_privacy(leaked_identifier, database=database)


def test_stale_and_missing_provenance_fixture_fails_closed():
    evidence_ref = {
        'message_ids': ['m1'],
        'messages': [{
            'message_id': 'm1',
            'membership_id': 'mem1',
            'source_record_keys': ['rk-old'],
            'source_snapshot_keys': ['snapshot-1'],
            'source_parser_versions': ['parser-1'],
        }],
    }
    current_rows = [{
        'message_id': 'm1',
        'membership_id': 'mem1',
        'conversation_id': 'c1',
    }]
    drifted_sources = {
        'm1': [{
            'source_record_key': 'rk-new',
            'source_snapshot_key': 'snapshot-1',
            'parser_version': 'parser-1',
        }],
    }

    stale = reconcile_a5_evidence_ref(evidence_ref, current_rows, drifted_sources)
    assert stale.status == STALE

    missing = reconcile_a5_evidence_ref(evidence_ref, [], {})
    assert missing.status == FAIL
