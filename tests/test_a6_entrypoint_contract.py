from pathlib import Path


def test_entrypoint_uses_runtime_v2_not_legacy_monkeypatches():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / "app.py").read_text(encoding="utf-8")
    runtime_ui = (root / "a6" / "runtime_ui.py").read_text(encoding="utf-8")

    assert "from a6.runtime_ui import main" in entrypoint
    assert "from a6 import app_legacy" not in entrypoint
    assert "from a6.app_legacy" not in entrypoint
    assert "_legacy." not in entrypoint

    assert "run_local_runtime" in runtime_ui
    assert "compile_packet_to_packs" in runtime_ui
    assert "enrich_analysis_packet_source_provenance" in runtime_ui
    assert "reconcile_a5_evidence_ref" in runtime_ui
    assert "run_local_a5" not in runtime_ui
