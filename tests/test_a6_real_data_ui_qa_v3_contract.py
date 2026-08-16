from __future__ import annotations

from pathlib import Path

from tools.a6_real_data_ui_qa_v3 import build_parser


def test_v3_browser_channel_is_explicit_and_optional():
    parser = build_parser()
    default = parser.parse_args(["--database", "messages.sqlite"])
    assert default.browser_channel is None
    assert default.conversation_id is None
    assert default.keep_screenshots is False

    local = parser.parse_args(
        [
            "--database",
            "messages.sqlite",
            "--conversation-id",
            "example-conversation",
            "--browser-channel",
            "chrome",
        ]
    )
    assert local.browser_channel == "chrome"
    assert local.conversation_id == "example-conversation"


def test_target_app_keeps_target_process_local():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "a6_real_data_target_app.py"
    ).read_text(encoding="utf-8")
    assert "ANALYZA_ZPRAV_CONVERSATION_ID" in source
    assert "conversation_id" in source
    assert "write_text" not in source


def test_v3_reports_privacy_safe_real_interaction_stages():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "a6_real_data_ui_qa_v3.py"
    ).read_text(encoding="utf-8")
    for stage in (
        "conversation_content",
        "graphs_tab_click",
        "graphs_content",
        "finding_select",
        "finding_evidence_button",
        "selected_messages_content",
        "analysis_content",
    ):
        assert stage in source
    assert 'page.get_by_role("tab", name="Konverzace", exact=True).click' not in source
