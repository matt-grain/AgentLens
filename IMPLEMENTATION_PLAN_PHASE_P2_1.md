# Phase P2.1: RAG Span Types + Evaluators

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Add `RETRIEVAL` and `EMBEDDING` span types so AgentLens can capture and evaluate RAG pipelines. Add 2 deterministic evaluators for retrieval quality. This brings AgentLens to parity with LangSmith/Langfuse/Phoenix on RAG observability.

## Files to Modify

### `src/agentlens/models/trace.py` (MODIFY)
**Changes:**
1. Add two new members to `SpanType`:
   ```python
   RETRIEVAL = "retrieval"
   EMBEDDING = "embedding"
   ```
2. Add output key conventions in the Span docstring:
   ```
   - RETRIEVAL: output={"documents": [{"id": "doc1", "content": "...", "score": 0.95}]}
   - EMBEDDING: output={"vector_dim": 1536, "model": "text-embedding-3-small"}
   ```

### `src/agentlens/evaluators/rag.py` (CREATE)
**Purpose:** RAG-specific evaluators for retrieval quality
**Classes:**

#### `RetrievalRelevanceEvaluator`
- `name = "retrieval_relevance"`
- `level = EvalLevel.BEHAVIOR`
- `evaluate(trace, expected)` logic:
  - Find all RETRIEVAL spans
  - If none found: return INFO "No retrieval spans in trace"
  - For each RETRIEVAL span, check `output.documents`:
    - If documents list is empty: score 0.0 (retrieval returned nothing)
    - Count documents with `score >= 0.5` (relevance threshold)
    - Score = relevant_docs / total_docs
  - Average across all RETRIEVAL spans
  - Pass if score >= 0.5
  - Evidence: list doc IDs and their scores

#### `ContextGroundingEvaluator`
- `name = "context_grounding"`
- `level = EvalLevel.RISK`
- `evaluate(trace, expected)` logic:
  - Find all RETRIEVAL spans and collect their document content
  - Find the final LLM_CALL span output content
  - Check if key phrases from the LLM output appear in retrieved documents
    - Extract sentences from LLM output (split on `. `)
    - For each sentence containing a factual claim (has numbers or proper nouns), check if any word sequence (3+ words) appears in any retrieved document content
  - Score = grounded_sentences / total_factual_sentences
  - If no RETRIEVAL spans: return INFO "No retrieval context to verify"
  - Pass if score >= 0.5
  - Severity: WARNING if partial, CRITICAL if score == 0 (answer has zero grounding)
  - Evidence: list ungrounded sentences

**Constraints:**
- Under 150 lines total
- Import only from `agentlens.models.*`
- No external dependencies (no embeddings, no LLM calls)
- Both evaluators are deterministic
**Reference:** Follow pattern in `src/agentlens/evaluators/risk.py` (same structure: name, level, evaluate method returning `list[EvalResult]`)

### `src/agentlens/evaluators/__init__.py` (MODIFY)
**Changes:**
1. In `default_evaluators()`, add imports and instances:
   ```python
   from agentlens.evaluators.rag import ContextGroundingEvaluator, RetrievalRelevanceEvaluator
   ```
   Add to the return list after the Risk section:
   ```python
   # RAG
   RetrievalRelevanceEvaluator(),
   ContextGroundingEvaluator(),
   ```

### `src/agentlens/__init__.py` (MODIFY)
**Changes:** Add `RetrievalRelevanceEvaluator` and `ContextGroundingEvaluator` to public exports if desired. Optional — evaluators are typically accessed via `default_evaluators()`.

## Test File

### `tests/test_evaluators/test_rag.py` (CREATE)
**Tests:**
- `test_retrieval_relevance_all_relevant_scores_1` — 3 docs all with score >= 0.5
- `test_retrieval_relevance_no_relevant_scores_0` — 3 docs all with score < 0.5
- `test_retrieval_relevance_mixed_scores_proportionally` — 1/3 relevant = ~0.33
- `test_retrieval_relevance_no_retrieval_spans_returns_info` — Trace with only LLM_CALL spans
- `test_retrieval_relevance_empty_documents_scores_0` — RETRIEVAL span with empty documents list
- `test_context_grounding_grounded_answer_passes` — LLM output contains phrases from retrieved docs
- `test_context_grounding_ungrounded_answer_fails` — LLM output has claims not in any retrieved doc
- `test_context_grounding_no_retrieval_returns_info` — No RETRIEVAL spans

**Fixture strategy:** Use `make_span` and `make_trace` from `tests/test_evaluators/conftest.py`. Create RETRIEVAL spans with `span_type=SpanType.RETRIEVAL` and `output={"documents": [...]}`.

## Verification

```bash
uv run pytest tests/test_evaluators/test_rag.py -v
uv run pytest tests/ -v  # all pass
uv run pyright src/
```
