"""RAG-specific evaluators for retrieval quality assessment."""

from __future__ import annotations

import re
from typing import Any, TypedDict, cast

from agentlens.models.evaluation import EvalLevel, EvalResult, EvalSeverity
from agentlens.models.expectation import TaskExpectation
from agentlens.models.trace import Span, SpanType, Trace

_PROPER_NOUN_PATTERN = re.compile(r"\b[A-Z][a-z]+\b")
_RELEVANCE_THRESHOLD: float = 0.5
_GROUNDING_WINDOW: int = 3


class _Document(TypedDict, total=False):
    id: str
    content: str
    score: float


def _retrieval_spans(trace: Trace) -> list[Span]:
    return [s for s in trace.spans if s.span_type == SpanType.RETRIEVAL]


def _get_documents(span: Span) -> list[_Document]:
    """Extract and validate the documents list from a RETRIEVAL span output."""
    raw: Any = (span.output or {}).get("documents", [])
    if not isinstance(raw, list):
        return []
    # Cast: each element entered via dict[str, Any]; we accept only well-formed dicts.
    # Any malformed entry is skipped downstream via isinstance checks.
    return cast("list[_Document]", raw)


def _score_documents(documents: list[_Document]) -> float:
    """Return the fraction of documents with score >= relevance threshold."""
    if not documents:
        return 0.0
    relevant = sum(
        1
        for doc in documents
        if isinstance(doc.get("score"), int | float) and float(doc.get("score", 0.0)) >= _RELEVANCE_THRESHOLD
    )
    return relevant / len(documents)


class RetrievalRelevanceEvaluator:
    """Measures the fraction of retrieved documents that are relevant (score >= 0.5)."""

    name: str = "retrieval_relevance"
    level: EvalLevel = EvalLevel.BEHAVIOR

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        spans = _retrieval_spans(trace)
        if not spans:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="No retrieval spans in trace.",
                    severity=EvalSeverity.INFO,
                )
            ]

        span_scores: list[float] = []
        evidence: list[str] = []

        for span in spans:
            documents = _get_documents(span)
            score = _score_documents(documents)
            span_scores.append(score)
            for doc in documents:
                doc_id: str = str(doc.get("id", "unknown"))
                doc_score: object = doc.get("score", "N/A")
                evidence.append(f"doc '{doc_id}': score={doc_score}")

        avg_score = sum(span_scores) / len(span_scores)
        passed = avg_score >= _RELEVANCE_THRESHOLD

        return [
            EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=round(avg_score, 4),
                passed=passed,
                message=f"Retrieval relevance: {avg_score:.0%} of documents above threshold.",
                severity=EvalSeverity.INFO if passed else EvalSeverity.WARNING,
                evidence=evidence,
            )
        ]


def _is_factual_sentence(sentence: str) -> bool:
    """Return True if the sentence contains digits or a proper noun."""
    if re.search(r"\d", sentence):
        return True
    return bool(_PROPER_NOUN_PATTERN.search(sentence))


def _is_grounded(sentence: str, doc_contents: list[str]) -> bool:
    """Return True if any consecutive 3-word window of sentence appears in any document."""
    words = sentence.split()
    if len(words) < _GROUNDING_WINDOW:
        return False
    for i in range(len(words) - _GROUNDING_WINDOW + 1):
        phrase = " ".join(words[i : i + _GROUNDING_WINDOW]).lower()
        if any(phrase in content.lower() for content in doc_contents):
            return True
    return False


class ContextGroundingEvaluator:
    """Checks whether factual claims in the LLM output are grounded in retrieved documents."""

    name: str = "context_grounding"
    level: EvalLevel = EvalLevel.RISK

    def evaluate(self, trace: Trace, expected: TaskExpectation | None = None) -> list[EvalResult]:
        spans = _retrieval_spans(trace)
        if not spans:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="No retrieval context to verify.",
                    severity=EvalSeverity.INFO,
                )
            ]

        doc_contents = self._collect_document_contents(spans)
        llm_output = self._final_llm_output(trace)
        if not llm_output:
            return [
                EvalResult(
                    evaluator_name=self.name,
                    level=self.level,
                    score=1.0,
                    passed=True,
                    message="No LLM output to verify.",
                    severity=EvalSeverity.INFO,
                )
            ]

        return [self._grade_output(llm_output, doc_contents)]

    def _collect_document_contents(self, spans: list[Span]) -> list[str]:
        contents: list[str] = []
        for span in spans:
            for doc in _get_documents(span):
                content = doc.get("content")
                if isinstance(content, str):
                    contents.append(content)
        return contents

    def _final_llm_output(self, trace: Trace) -> str:
        llm_spans = [s for s in trace.spans if s.span_type == SpanType.LLM_CALL]
        if not llm_spans:
            return ""
        raw: Any = (llm_spans[-1].output or {}).get("content", "")
        return raw if isinstance(raw, str) else ""

    def _grade_output(self, llm_output: str, doc_contents: list[str]) -> EvalResult:
        sentences = [s.strip() for s in llm_output.split(". ") if s.strip()]
        factual = [s for s in sentences if _is_factual_sentence(s)]

        if not factual:
            return EvalResult(
                evaluator_name=self.name,
                level=self.level,
                score=1.0,
                passed=True,
                message="No factual claims detected in LLM output.",
                severity=EvalSeverity.INFO,
            )

        ungrounded = [s for s in factual if not _is_grounded(s, doc_contents)]
        score = 1.0 - len(ungrounded) / len(factual)
        passed = score >= _RELEVANCE_THRESHOLD

        if not passed and score == 0.0:
            severity = EvalSeverity.CRITICAL
        elif not passed:
            severity = EvalSeverity.WARNING
        else:
            severity = EvalSeverity.INFO

        return EvalResult(
            evaluator_name=self.name,
            level=self.level,
            score=round(score, 4),
            passed=passed,
            message=f"Context grounding: {len(ungrounded)}/{len(factual)} factual sentences ungrounded.",
            severity=severity,
            evidence=ungrounded,
        )
