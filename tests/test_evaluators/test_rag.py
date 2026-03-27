"""Tests for RAG evaluators: RetrievalRelevanceEvaluator and ContextGroundingEvaluator."""

from __future__ import annotations

import pytest

from agentlens.evaluators.rag import ContextGroundingEvaluator, RetrievalRelevanceEvaluator
from agentlens.models.evaluation import EvalSeverity
from agentlens.models.trace import SpanType
from tests.test_evaluators.conftest import make_span, make_trace

# ---------------------------------------------------------------------------
# RetrievalRelevanceEvaluator
# ---------------------------------------------------------------------------


def test_retrieval_relevance_all_relevant_scores_1() -> None:
    # Arrange
    documents = [
        {"id": "doc1", "content": "alpha", "score": 0.9},
        {"id": "doc2", "content": "beta", "score": 0.8},
        {"id": "doc3", "content": "gamma", "score": 0.7},
    ]
    span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": documents})
    trace = make_trace([span])
    evaluator = RetrievalRelevanceEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    assert len(results) == 1
    result = results[0]
    assert result.passed is True
    assert result.score == pytest.approx(1.0)
    assert result.severity == EvalSeverity.INFO


def test_retrieval_relevance_no_relevant_scores_0() -> None:
    # Arrange
    documents = [
        {"id": "doc1", "content": "alpha", "score": 0.1},
        {"id": "doc2", "content": "beta", "score": 0.2},
        {"id": "doc3", "content": "gamma", "score": 0.3},
    ]
    span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": documents})
    trace = make_trace([span])
    evaluator = RetrievalRelevanceEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is False
    assert result.score == pytest.approx(0.0)
    assert result.severity == EvalSeverity.WARNING


def test_retrieval_relevance_mixed_scores_proportionally() -> None:
    # Arrange — 1 out of 3 documents is relevant → score ≈ 0.333
    documents = [
        {"id": "doc1", "content": "alpha", "score": 0.9},
        {"id": "doc2", "content": "beta", "score": 0.2},
        {"id": "doc3", "content": "gamma", "score": 0.1},
    ]
    span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": documents})
    trace = make_trace([span])
    evaluator = RetrievalRelevanceEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is False
    assert result.score == pytest.approx(1 / 3, rel=1e-3)


def test_retrieval_relevance_no_retrieval_spans_returns_info() -> None:
    # Arrange — trace contains only LLM_CALL spans
    span = make_span("l1", SpanType.LLM_CALL, "llm", output={"content": "hello"})
    trace = make_trace([span])
    evaluator = RetrievalRelevanceEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is True
    assert result.severity == EvalSeverity.INFO
    assert "No retrieval spans" in result.message


def test_retrieval_relevance_empty_documents_scores_0() -> None:
    # Arrange — RETRIEVAL span with empty documents list
    span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": []})
    trace = make_trace([span])
    evaluator = RetrievalRelevanceEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is False
    assert result.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# ContextGroundingEvaluator
# ---------------------------------------------------------------------------


def test_context_grounding_grounded_answer_passes() -> None:
    # Arrange — LLM output phrases appear verbatim in retrieved document
    doc_content = "The unemployment rate in Germany was 5.6 percent in January 2024."
    documents = [{"id": "doc1", "content": doc_content, "score": 0.9}]
    retrieval_span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": documents})
    # LLM sentence contains a number and the 3-word sequence "unemployment rate in" is in the doc
    llm_span = make_span(
        "l1",
        SpanType.LLM_CALL,
        "llm",
        output={"content": "The unemployment rate in Germany was 5.6 percent in January 2024."},
        offset_ms=200,
    )
    trace = make_trace([retrieval_span, llm_span])
    evaluator = ContextGroundingEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is True
    assert result.score == pytest.approx(1.0)


def test_context_grounding_ungrounded_answer_fails() -> None:
    # Arrange — LLM output makes a numeric claim absent from retrieved docs
    documents = [{"id": "doc1", "content": "The sky is blue on clear days.", "score": 0.9}]
    retrieval_span = make_span("r1", SpanType.RETRIEVAL, "retrieve", output={"documents": documents})
    # Contains "42 million users" — a numeric claim not in the document
    llm_span = make_span(
        "l1",
        SpanType.LLM_CALL,
        "llm",
        output={"content": "There are 42 million users registered on the platform."},
        offset_ms=200,
    )
    trace = make_trace([retrieval_span, llm_span])
    evaluator = ContextGroundingEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is False
    assert result.score == pytest.approx(0.0)
    assert result.severity == EvalSeverity.CRITICAL
    assert len(result.evidence) >= 1


def test_context_grounding_no_retrieval_returns_info() -> None:
    # Arrange — no RETRIEVAL spans in the trace
    llm_span = make_span("l1", SpanType.LLM_CALL, "llm", output={"content": "The answer is 42."})
    trace = make_trace([llm_span])
    evaluator = ContextGroundingEvaluator()

    # Act
    results = evaluator.evaluate(trace)

    # Assert
    result = results[0]
    assert result.passed is True
    assert result.severity == EvalSeverity.INFO
    assert "No retrieval context" in result.message
