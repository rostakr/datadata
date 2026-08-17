from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from .analyzer import AIAnalyzer
from .cache import AnalysisCache, make_context_hash
from .context_builder import ContextBuilder
from .integration_a6 import (
    A6PacketMessageSource,
    candidate_from_a6_packet,
    messages_from_a6_packet,
    request_from_a6_packet,
)
from .models import (
    AIAnalysisResult,
    AnalysisContext,
    AnalysisExecution,
    AnalysisMode,
    AnalysisStatus,
    AnalysisType,
    EvidenceRef,
    MessageRecord,
)
from .prompts import RESULT_SCHEMA_DESCRIPTION, build_repair_prompt
from .providers.base import AIProvider, ProviderError, ProviderTimeout, ProviderUnavailable
from .validator import ValidationError, parse_and_validate_result


A6_EVIDENCE_CHUNK_SIZE = 120
A5_CONTEXT_MESSAGE_LIMIT = 180
SYNTHESIS_PROMPT_VERSION = "a5-v1-validated-chunk-synthesis"

SYNTHESIS_SYSTEM_PROMPT = """You synthesize already validated A5 chunk results.
You do NOT receive the original message text or the full conversation context.
Rules:
1. Use only claims, uncertainty and message IDs present in the supplied validated chunk results.
2. Every assertion-bearing output field must cite one or more IDs from allowed_evidence_message_ids.
3. Never invent a message ID, quote, event, metric, motive, diagnosis or external fact.
4. Do not turn a chunk-level interpretation into an observable fact.
5. Preserve disagreements, alternative explanations and unknowns across chunks.
6. Cross-chunk patterns may be stated only when supported by evidence from multiple supplied chunks.
7. No deterministic metrics are supplied to this synthesis step; omit metric_refs or use an empty array.
8. Confidence reflects support in the supplied validated chunk results, not hidden-state probability.
9. Return JSON only and match the requested result structure.
The application will independently validate every cited message ID and rematerialize evidence from canonical data after your response.
"""


@dataclass(frozen=True)
class ChunkExecutionSummary:
    chunk_index: int
    evidence_count: int
    status: AnalysisStatus
    context_hash: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "evidence_count": self.evidence_count,
            "status": self.status.value,
            "context_hash": self.context_hash,
            "error": self.error,
        }


@dataclass(frozen=True)
class ChunkedAnalysisExecution:
    status: AnalysisStatus
    result: AIAnalysisResult | None
    context_hash: str
    error: str | None
    selected_message_count: int
    evidence_chunk_size: int
    chunk_count: int
    chunks: tuple[ChunkExecutionSummary, ...]
    synthesis_used: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "context_hash": self.context_hash,
            "error": self.error,
            "result": self.result.to_dict() if self.result is not None else None,
            "chunking": {
                "enabled": self.chunk_count > 1,
                "selected_message_count": self.selected_message_count,
                "evidence_chunk_size": self.evidence_chunk_size,
                "chunk_count": self.chunk_count,
                "synthesis_used": self.synthesis_used,
                "synthesis_status": self.status.value if self.synthesis_used else None,
                "chunks": [item.to_dict() for item in self.chunks],
            },
        }


def chunk_a6_packet(
    packet: Mapping[str, Any],
    *,
    max_evidence_per_chunk: int = A6_EVIDENCE_CHUNK_SIZE,
) -> tuple[dict[str, Any], ...]:
    """Split A6 selected evidence chronologically without dropping any selection.

    The source packet is validated before splitting. Every child packet retains
    the complete original local packet context/provenance, but its explicit
    selected evidence is limited to one deterministic chronological chunk.
    ContextBuilder is responsible for reducing the provider-visible context.
    """

    if max_evidence_per_chunk < 1:
        raise ValueError("max_evidence_per_chunk must be positive")

    candidate = candidate_from_a6_packet(packet)
    messages = messages_from_a6_packet(packet)
    selected = set(candidate.evidence_message_ids)
    ordered_selected = [message.id for message in messages if message.id in selected]
    if len(ordered_selected) != len(candidate.evidence_message_ids):
        raise ValueError("A6 selected evidence could not be ordered losslessly")

    chunk_ids = [
        ordered_selected[index : index + max_evidence_per_chunk]
        for index in range(0, len(ordered_selected), max_evidence_per_chunk)
    ]
    chunk_count = len(chunk_ids)
    result: list[dict[str, Any]] = []
    covered: list[str] = []

    for index, ids in enumerate(chunk_ids, start=1):
        child = deepcopy(dict(packet))
        child["selected_message_ids"] = list(ids)
        child["selected_message_count"] = len(ids)
        child["chunking"] = {
            "parent_selected_message_count": len(ordered_selected),
            "chunk_index": index,
            "chunk_count": chunk_count,
            "max_evidence_per_chunk": max_evidence_per_chunk,
        }
        raw_messages = child.get("messages")
        if isinstance(raw_messages, list):
            child["messages"] = [
                {
                    **dict(raw),
                    "selected": str(raw.get("message_id")) in set(ids),
                }
                if isinstance(raw, Mapping)
                else raw
                for raw in raw_messages
            ]
        result.append(child)
        covered.extend(ids)

    if covered != ordered_selected or len(set(covered)) != len(covered):
        raise ValueError("A6 chunking did not preserve selected evidence exactly once")
    return tuple(result)


def _compact_evidence(ref: EvidenceRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return {
        "message_ids": list(ref.message_ids),
        "description": ref.description,
    }


def _compact_result(result: AIAnalysisResult) -> dict[str, Any]:
    return {
        "summary": {
            "text": result.summary,
            "evidence": _compact_evidence(result.summary_evidence),
        },
        "observations": [
            {
                "text": item.text,
                "strength": item.strength,
                "evidence": _compact_evidence(item.evidence),
            }
            for item in result.observations
        ],
        "interpretations": [
            {
                "text": item.text,
                "confidence": item.confidence,
                "evidence_message_ids": list(item.evidence_message_ids),
            }
            for item in result.interpretations
        ],
        "patterns": [
            {
                "pattern_type": item.pattern_type,
                "description": item.description,
                "occurrences": item.occurrences,
                "confidence": item.confidence,
                "evidence_message_ids": list(item.evidence_message_ids),
            }
            for item in result.patterns
        ],
        "turning_points": [
            {
                "text": text,
                "evidence": _compact_evidence(evidence),
            }
            for text, evidence in zip(
                result.turning_points,
                result.turning_point_evidence,
                strict=True,
            )
        ],
        "participant_p1": (
            {
                "text": result.participant_p1,
                "evidence": _compact_evidence(result.participant_p1_evidence),
            }
            if result.participant_p1 is not None
            else None
        ),
        "participant_p2": (
            {
                "text": result.participant_p2,
                "evidence": _compact_evidence(result.participant_p2_evidence),
            }
            if result.participant_p2 is not None
            else None
        ),
        "shared_dynamic": (
            {
                "text": result.shared_dynamic,
                "evidence": _compact_evidence(result.shared_dynamic_evidence),
            }
            if result.shared_dynamic is not None
            else None
        ),
        "alternative_explanations": list(result.alternative_explanations),
        "unknowns": list(result.unknowns),
        "overall_confidence": result.overall_confidence,
    }


def _result_evidence_ids(result: AIAnalysisResult) -> set[str]:
    ids: set[str] = set()

    def add(ref: EvidenceRef | None) -> None:
        if ref is not None:
            ids.update(ref.message_ids)

    add(result.summary_evidence)
    for item in result.observations:
        add(item.evidence)
    for item in result.interpretations:
        ids.update(item.evidence_message_ids)
        add(item.evidence)
    for item in result.patterns:
        ids.update(item.evidence_message_ids)
        add(item.evidence)
    for ref in result.turning_point_evidence:
        add(ref)
    add(result.participant_p1_evidence)
    add(result.participant_p2_evidence)
    add(result.shared_dynamic_evidence)
    return ids


def _build_synthesis_validation_context(
    packet: Mapping[str, Any],
    chunk_results: Sequence[AIAnalysisResult],
    *,
    analysis_type: AnalysisType,
    mode: AnalysisMode,
) -> AnalysisContext:
    """Build a local validation-only context from already cited evidence.

    This context is NEVER serialized into the synthesis provider prompt. It is
    used only after the model responds, so the validator can restrict final
    citations to message IDs that were already cited by validated chunk results
    and rematerialize their immutable source-derived evidence snapshots.
    """

    messages = messages_from_a6_packet(packet)
    parent = candidate_from_a6_packet(packet)
    allowed_ids: set[str] = set()
    for result in chunk_results:
        allowed_ids.update(_result_evidence_ids(result))
    if not allowed_ids:
        raise ValidationError("validated chunk results contain no evidence IDs")

    selected = tuple(message for message in messages if message.id in allowed_ids)
    if len(selected) != len(allowed_ids):
        raise ValidationError("chunk synthesis evidence is missing from the A6 packet")

    start_ts = parent.start_ts
    end_ts = parent.end_ts
    return AnalysisContext(
        conversation_id=parent.conversation_id,
        analysis_type=analysis_type,
        mode=mode,
        requested_start_ts=start_ts,
        requested_end_ts=end_ts,
        context_start_ts=start_ts,
        context_end_ts=end_ts,
        cutoff_ts=end_ts if mode == AnalysisMode.BLIND else None,
        messages=selected,
        evidence_message_ids=tuple(message.id for message in selected),
        metrics_before={},
        metrics_during={},
        metrics_after={},
        detected_signals=("validated_chunk_synthesis",),
        candidate_provenance={
            "source": "a6_validated_chunk_synthesis",
            "chunk_count": len(chunk_results),
        },
        available_message_count=len(selected),
        omitted_message_count=0,
        omitted_message_ids=(),
        omitted_message_ids_sha256=None,
        missing_evidence_message_ids=(),
        quality_warnings=(),
    )


def _build_synthesis_input(
    validation_context: AnalysisContext,
    chunk_results: Sequence[AIAnalysisResult],
    *,
    analysis_type: AnalysisType,
    mode: AnalysisMode,
    user_question: str | None,
) -> dict[str, Any]:
    # Only IDs and already-validated model claims are serialized here. Raw
    # MessageRecord.text/source provenance are intentionally absent.
    return {
        "analysis_type": analysis_type.value,
        "mode": mode.value,
        "user_question": user_question or None,
        "chunk_count": len(chunk_results),
        "allowed_evidence_message_ids": [
            message.id for message in validation_context.messages
        ],
        "validated_chunk_results": [
            {
                "chunk_index": index,
                "result": _compact_result(result),
            }
            for index, result in enumerate(chunk_results, start=1)
        ],
        "required_output_shape": RESULT_SCHEMA_DESCRIPTION,
    }


def _store_synthesis_failure(
    cache: AnalysisCache | None,
    *,
    context_hash: str,
    conversation_id: str,
    analysis_type: AnalysisType,
    mode: AnalysisMode,
    provider: AIProvider,
    status: AnalysisStatus,
    error: str,
) -> None:
    if cache is None:
        return
    cache.put(
        context_hash=context_hash,
        conversation_id=conversation_id,
        analysis_type=analysis_type.value,
        mode=mode.value,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        prompt_version=SYNTHESIS_PROMPT_VERSION,
        status=status,
        result=None,
        error=error,
    )


def _synthesize_chunk_results(
    packet: Mapping[str, Any],
    chunk_results: Sequence[AIAnalysisResult],
    *,
    provider: AIProvider,
    analysis_type: AnalysisType,
    mode: AnalysisMode,
    user_question: str | None,
    cache: AnalysisCache | None,
    force_refresh: bool,
) -> AnalysisExecution:
    validation_context = _build_synthesis_validation_context(
        packet,
        chunk_results,
        analysis_type=analysis_type,
        mode=mode,
    )
    synthesis_input = _build_synthesis_input(
        validation_context,
        chunk_results,
        analysis_type=analysis_type,
        mode=mode,
        user_question=user_question,
    )
    context_hash = make_context_hash(
        context_payload={"validated_chunk_synthesis": synthesis_input},
        analysis_type=analysis_type.value,
        mode=mode.value,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        prompt_version=SYNTHESIS_PROMPT_VERSION,
    )

    if cache is not None and not force_refresh:
        cached = cache.get(context_hash)
        if cached is not None:
            return AnalysisExecution(
                AnalysisStatus.CACHE_HIT,
                cached,
                context_hash,
            )

    user_prompt = (
        "SYNTHESIS TASK:\nCreate one cautious result from the validated chunk results below. "
        "Do not infer from messages you have not been shown and do not invent evidence.\n\n"
        + json.dumps(synthesis_input, ensure_ascii=False, indent=2)
    )
    try:
        raw = provider.analyze(
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except ProviderTimeout as exc:
        error = str(exc)
        _store_synthesis_failure(
            cache,
            context_hash=context_hash,
            conversation_id=validation_context.conversation_id,
            analysis_type=analysis_type,
            mode=mode,
            provider=provider,
            status=AnalysisStatus.ANALYSIS_TIMEOUT,
            error=error,
        )
        return AnalysisExecution(AnalysisStatus.ANALYSIS_TIMEOUT, None, context_hash, error)
    except ProviderUnavailable as exc:
        error = str(exc)
        _store_synthesis_failure(
            cache,
            context_hash=context_hash,
            conversation_id=validation_context.conversation_id,
            analysis_type=analysis_type,
            mode=mode,
            provider=provider,
            status=AnalysisStatus.MODEL_UNAVAILABLE,
            error=error,
        )
        return AnalysisExecution(AnalysisStatus.MODEL_UNAVAILABLE, None, context_hash, error)
    except ProviderError as exc:
        error = str(exc)
        _store_synthesis_failure(
            cache,
            context_hash=context_hash,
            conversation_id=validation_context.conversation_id,
            analysis_type=analysis_type,
            mode=mode,
            provider=provider,
            status=AnalysisStatus.INVALID_OUTPUT,
            error=error,
        )
        return AnalysisExecution(AnalysisStatus.INVALID_OUTPUT, None, context_hash, error)

    try:
        result = parse_and_validate_result(raw, validation_context)
    except ValidationError as first_error:
        repair_prompt = build_repair_prompt(user_prompt, raw, str(first_error))
        try:
            repaired = provider.analyze(
                system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
            )
        except ProviderTimeout as exc:
            error = str(exc)
            status = AnalysisStatus.ANALYSIS_TIMEOUT
            _store_synthesis_failure(
                cache,
                context_hash=context_hash,
                conversation_id=validation_context.conversation_id,
                analysis_type=analysis_type,
                mode=mode,
                provider=provider,
                status=status,
                error=error,
            )
            return AnalysisExecution(status, None, context_hash, error)
        except ProviderUnavailable as exc:
            error = str(exc)
            status = AnalysisStatus.MODEL_UNAVAILABLE
            _store_synthesis_failure(
                cache,
                context_hash=context_hash,
                conversation_id=validation_context.conversation_id,
                analysis_type=analysis_type,
                mode=mode,
                provider=provider,
                status=status,
                error=error,
            )
            return AnalysisExecution(status, None, context_hash, error)
        except ProviderError as exc:
            error = str(exc)
            status = AnalysisStatus.INVALID_OUTPUT
            _store_synthesis_failure(
                cache,
                context_hash=context_hash,
                conversation_id=validation_context.conversation_id,
                analysis_type=analysis_type,
                mode=mode,
                provider=provider,
                status=status,
                error=error,
            )
            return AnalysisExecution(status, None, context_hash, error)
        try:
            result = parse_and_validate_result(repaired, validation_context)
        except ValidationError as second_error:
            error = (
                f"initial synthesis validation: {first_error}; "
                f"repair synthesis validation: {second_error}"
            )
            status = AnalysisStatus.FAILED_VALIDATION
            _store_synthesis_failure(
                cache,
                context_hash=context_hash,
                conversation_id=validation_context.conversation_id,
                analysis_type=analysis_type,
                mode=mode,
                provider=provider,
                status=status,
                error=error,
            )
            return AnalysisExecution(status, None, context_hash, error)

    if cache is not None:
        cache.put(
            context_hash=context_hash,
            conversation_id=validation_context.conversation_id,
            analysis_type=analysis_type.value,
            mode=mode.value,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            prompt_version=SYNTHESIS_PROMPT_VERSION,
            status=AnalysisStatus.COMPLETED,
            result=result,
        )
    return AnalysisExecution(AnalysisStatus.COMPLETED, result, context_hash)


def analyze_a6_packet_chunked(
    packet: Mapping[str, Any],
    *,
    provider: AIProvider,
    analysis_type: AnalysisType = AnalysisType.SEGMENT,
    mode: AnalysisMode = AnalysisMode.BLIND,
    user_question: str | None = None,
    cache: AnalysisCache | None = None,
    force_refresh: bool = False,
    max_evidence_per_chunk: int = A6_EVIDENCE_CHUNK_SIZE,
    max_context_messages: int = A5_CONTEXT_MESSAGE_LIMIT,
) -> ChunkedAnalysisExecution:
    """Run bounded A5 over an A6 packet and synthesize validated chunks.

    Provider preflight is intentionally the caller's responsibility so an
    Ollama-specific readiness check can happen exactly once before any evidence
    prompt. This function itself is provider-agnostic and never introduces a
    fallback provider.
    """

    if max_context_messages < 1:
        raise ValueError("max_context_messages must be positive")
    if not 1 <= max_evidence_per_chunk <= max_context_messages:
        raise ValueError(
            "max_evidence_per_chunk must be between 1 and max_context_messages"
        )

    parent = candidate_from_a6_packet(packet)
    child_packets = chunk_a6_packet(
        packet,
        max_evidence_per_chunk=max_evidence_per_chunk,
    )
    summaries: list[ChunkExecutionSummary] = []
    completed_results: list[AIAnalysisResult] = []

    for index, child in enumerate(child_packets, start=1):
        source = A6PacketMessageSource.from_packet(child)
        candidate = candidate_from_a6_packet(child)
        request = request_from_a6_packet(
            child,
            analysis_type=analysis_type,
            mode=mode,
            user_question=user_question,
        )
        if force_refresh:
            request = type(request)(
                conversation_id=request.conversation_id,
                analysis_type=request.analysis_type,
                start_ts=request.start_ts,
                end_ts=request.end_ts,
                mode=request.mode,
                candidate_id=request.candidate_id,
                user_question=request.user_question,
                force_refresh=True,
            )
        execution = AIAnalyzer(
            context_builder=ContextBuilder(
                source,
                max_messages=max_context_messages,
            ),
            provider=provider,
            cache=cache,
        ).analyze(request, candidate)
        summaries.append(
            ChunkExecutionSummary(
                chunk_index=index,
                evidence_count=len(candidate.evidence_message_ids),
                status=execution.status,
                context_hash=execution.context_hash,
                error=execution.error,
            )
        )
        if execution.status not in {AnalysisStatus.COMPLETED, AnalysisStatus.CACHE_HIT}:
            return ChunkedAnalysisExecution(
                status=execution.status,
                result=None,
                context_hash=execution.context_hash,
                error=f"A5 chunk {index}/{len(child_packets)} failed: {execution.error or execution.status.value}",
                selected_message_count=len(parent.evidence_message_ids),
                evidence_chunk_size=max_evidence_per_chunk,
                chunk_count=len(child_packets),
                chunks=tuple(summaries),
                synthesis_used=False,
            )
        if execution.result is None:
            return ChunkedAnalysisExecution(
                status=AnalysisStatus.FAILED_VALIDATION,
                result=None,
                context_hash=execution.context_hash,
                error=f"A5 chunk {index}/{len(child_packets)} completed without a result",
                selected_message_count=len(parent.evidence_message_ids),
                evidence_chunk_size=max_evidence_per_chunk,
                chunk_count=len(child_packets),
                chunks=tuple(summaries),
                synthesis_used=False,
            )
        completed_results.append(execution.result)

    if len(completed_results) == 1:
        only = summaries[0]
        return ChunkedAnalysisExecution(
            status=only.status,
            result=completed_results[0],
            context_hash=only.context_hash,
            error=None,
            selected_message_count=len(parent.evidence_message_ids),
            evidence_chunk_size=max_evidence_per_chunk,
            chunk_count=1,
            chunks=tuple(summaries),
            synthesis_used=False,
        )

    synthesis = _synthesize_chunk_results(
        packet,
        completed_results,
        provider=provider,
        analysis_type=analysis_type,
        mode=mode,
        user_question=user_question,
        cache=cache,
        force_refresh=force_refresh,
    )
    return ChunkedAnalysisExecution(
        status=synthesis.status,
        result=synthesis.result,
        context_hash=synthesis.context_hash,
        error=synthesis.error,
        selected_message_count=len(parent.evidence_message_ids),
        evidence_chunk_size=max_evidence_per_chunk,
        chunk_count=len(child_packets),
        chunks=tuple(summaries),
        synthesis_used=True,
    )
