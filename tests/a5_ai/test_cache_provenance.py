from __future__ import annotations

from analyzazprav.a5_ai import (
    AIAnalysisResult,
    AnalysisCache,
    AnalysisStatus,
    EvidenceRef,
    MessageEvidence,
    MetricEvidence,
)


def test_cache_hit_preserves_message_and_metric_provenance(tmp_path) -> None:
    evidence = EvidenceRef(
        message_ids=("m1",),
        description="direct",
        messages=(
            MessageEvidence(
                message_id="m1",
                timestamp="2025-01-01T12:00:00+00:00",
                sender_id="P1",
                excerpt="synthetic",
                membership_id="membership-1",
                source_record_keys=("record-1",),
                source_snapshot_keys=("snapshot-1",),
                source_parser_versions=("parser-1",),
            ),
        ),
        metrics=(
            MetricEvidence(
                phase="during",
                name="message_count",
                value=3.0,
                analytics_run_id="analytics-run",
                analytics_version="analytics-v1",
                analysis_signature="signature",
                source_fingerprint="fingerprint",
                processing_run_id="processing-run",
            ),
        ),
    )
    result = AIAnalysisResult(
        summary="synthetic summary",
        summary_evidence=evidence,
        overall_confidence=0.8,
    )
    cache = AnalysisCache(tmp_path / "a5.sqlite")
    cache.put(
        context_hash="context-hash",
        conversation_id="conversation-test",
        analysis_type="segment",
        mode="blind",
        provider_name="static",
        model_name="test-model",
        prompt_version="test-prompt",
        status=AnalysisStatus.COMPLETED,
        result=result,
    )

    restored = cache.get("context-hash")

    assert restored is not None
    restored_message = restored.summary_evidence.messages[0]
    assert restored_message.membership_id == "membership-1"
    assert restored_message.source_record_keys == ("record-1",)
    assert restored_message.source_snapshot_keys == ("snapshot-1",)
    assert restored_message.source_parser_versions == ("parser-1",)
    restored_metric = restored.summary_evidence.metrics[0]
    assert restored_metric.analytics_run_id == "analytics-run"
    assert restored_metric.analytics_version == "analytics-v1"
    assert restored_metric.analysis_signature == "signature"
    assert restored_metric.source_fingerprint == "fingerprint"
    assert restored_metric.processing_run_id == "processing-run"
