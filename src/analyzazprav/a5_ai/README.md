# A5 selective AI analysis

A5 is the interpretive layer of Analyzazprav. It never replaces deterministic A2–A4 processing. It receives only a bounded, relevant context and returns structured, evidence-backed interpretations.

## Core guarantees

- local-first provider abstraction; Ollama is the production local implementation
- deterministic candidate selection before AI inference
- chronological context with physical blind-mode cutoffs
- bounded context reduction that preserves explicit evidence
- exactly one repair attempt after invalid model output
- cache keyed by context, analysis type, mode, provider/model and prompt version
- every material claim must resolve to supplied source evidence
- invalid or duplicate evidence IDs fail closed
- no cloud fallback

## Evidence chain

The model is allowed to cite only existing message IDs and existing deterministic metric references. After validation, A5 enriches those references from `AnalysisContext` with the authoritative message timestamp, membership, source provenance, sender ID, safe excerpt and metric value. The model therefore cannot invent provenance metadata.

Assertion-bearing synthesis retains A6-compatible text fields with parallel source-derived evidence refs:

- `summary` + `summary_evidence`
- `turning_points` + `turning_point_evidence`
- `participant_p1` + `participant_p1_evidence`
- `participant_p2` + `participant_p2_evidence`
- `shared_dynamic` + `shared_dynamic_evidence`

Ordinary analysis prompt/cache contract: `a5-v4-provenance-reduction`.
Chunk synthesis prompt/cache contract: `a5-v1-validated-chunk-synthesis`.

## A2 handoff

`A2SQLiteMessageSource` reads canonical analytical views in read-only mode and provides message IDs, participant IDs, UTC timestamps, reply relations, attachment MIME types and edited/deleted flags.

## A4 v6 handoff

The current A4 contract is used as a deterministic candidate index. A5 adapters accept:

- `ConflictCandidate` → `conflict`
- `ChangePoint` → `change_point`
- `EngagementPeriodSignal` → `engagement_signal`
- `DyadicRegime` → `dyadic_regime`
- `TopicCandidate` → `lexical_topic`
- `AnalyticMessage` → bounded A5 message context

A4 metric names, directions and regime labels remain deterministic source signals; A5 does not silently reinterpret them as motives or psychological facts.

For ordinary candidates, all A4 `source_message_ids` are preserved directly as A5 evidence IDs. An oversized `lexical_topic` is the one intentional structural exception: the authoritative A4 topic row and its complete `source_message_ids` remain unchanged, while `A4SQLiteCandidateSource` creates a deterministic chronological partition for A5. Each chunk contains at most 120 explicit evidence messages, keeps `candidate_type=lexical_topic`, carries stable parent/chunk metadata, and all chunks together must cover the original A4 evidence exactly once. No evidence is sampled or silently discarded, and the global `ContextBuilder.max_messages` limit is not increased.

The chunk size deliberately leaves room inside the 180-message A5 context budget for neighboring context around explicit evidence. `ContextBuilder` still treats every evidence ID inside an individual chunk as an absolute constraint.

`A4SQLiteCandidateSource` reads the published `analysis_a4_*` SQLite views directly in read-only mode. Malformed JSON and duplicate source IDs fail closed. Missing optional views only disable that candidate type. Oversized topic chunking also fails closed if any topic evidence ID cannot be resolved to a timestamped canonical analytical message.

Lexical topic candidates remain explicitly lexical (`lexical_ngram_v1`). A5 may interpret their surrounding message evidence, but the candidate itself is not promoted to semantic truth.

## A6 live local handoff

`integration_a6.py` accepts A6 `analysis_packet` schema v1. Selected message IDs become explicit manual evidence. Duplicate packet message IDs, duplicate selected IDs, mixed conversations or incomplete required provenance are rejected before provider/network work.

`orchestrator.py` is the production A6 execution path:

1. validate the complete A6 packet and provenance;
2. order selected evidence chronologically;
3. split selections larger than 120 messages into lossless chunks of at most 120 evidence messages;
4. run each chunk through the existing `ContextBuilder(max_messages=180)`, `AIAnalyzer` and validator;
5. stop fail-closed if any chunk fails;
6. for multiple successful chunks, send only validated chunk-level claims plus their cited message IDs to a synthesis call;
7. validate final synthesis citations against a local validation-only context containing only IDs already cited by validated chunk outputs;
8. rematerialize final message evidence from canonical A6 packet data, including membership/source provenance.

The synthesis provider prompt never contains the complete A6 packet or the original full/raw message context. It receives already validated model claims and evidence IDs only. The validation-only context is never serialized into the provider prompt.

`a6/a5_bridge.py` performs Ollama `/api/tags` preflight once before evidence is sent to `/api/chat`. The exact requested model must already be installed locally. There is no automatic model pull and no cloud fallback.

A5 results are cached in a private local SQLite cache outside the repository, defaulting to `~/.datadata/cache/a5.sqlite`. `ANALYZA_ZPRAV_A5_CACHE` may override the path. Cache hits preserve the same materialized membership/source and metric provenance as fresh results.

A6 renders a privacy-safe chunk summary (`část`, evidence count, status) and then the same structured final result/evidence/source drill-down used for ordinary one-chunk analysis.

## Golden deterministic E2E slice

`tests/a5_ai/test_golden_e2e.py` validates one synthetic SQLite database through the full A5 integration boundary:

`A4 analysis_a4_events -> A4SQLiteCandidateSource -> A2 analysis_messages -> ContextBuilder -> StaticProvider -> validated A5 result -> A6 analysis_packet candidate`

The test proves that the same canonical message IDs survive from the A4 finding through source-derived A5 evidence and into the A6 handoff. It also verifies deterministic metric evidence (`conflict_score`) and source-derived sender/timestamp/excerpt data without any external AI service.

`tests/a5_ai/test_a4_topic_chunking.py` verifies that oversized A4 lexical-topic evidence is chronologically partitioned without loss or duplication and that every resulting chunk stays within the bounded A5 context contract.

`tests/a5_ai/test_a6_chunked_orchestrator.py` verifies the real A6 execution boundary with synthetic data: 250 selected messages become `120 + 120 + 10`, the synthesis prompt contains no original raw message text, final synthesis cannot cite an ID absent from validated chunk evidence, and a failing chunk prevents synthesis.

`tests/a5_ai/test_cache_provenance.py` verifies that cache hits preserve materialized evidence provenance.

## Failure isolation

If the model is unavailable, times out, a chunk fails, synthesis cites invalid evidence or model JSON cannot be repaired, A5 returns an explicit failure status. A1–A4 and the non-AI parts of A6 remain usable; AI is enrichment, never a data-path dependency.
