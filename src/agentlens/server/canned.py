"""Canned responses for mock mode demo scenarios."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CannedResponse(BaseModel, frozen=True):
    content: str
    # Plain dicts — serialize directly into OpenAI-compatible JSON without extra conversion.
    tool_calls: list[dict[str, Any]] = Field(default_factory=lambda: [])
    usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 100, "completion_tokens": 50})


class CannedRegistry:
    """Singleton registry for ordered per-scenario canned responses."""

    def __init__(self) -> None:
        self.responses: dict[str, list[CannedResponse]] = {}
        self._index: dict[str, int] = {}

    def register(self, scenario: str, responses: list[CannedResponse]) -> None:
        self.responses[scenario] = responses
        self._index[scenario] = 0

    def next_response(self, scenario: str) -> CannedResponse:
        items = self.responses[scenario]
        idx = self._index.get(scenario, 0)
        response = items[idx % len(items)]
        self._index[scenario] = (idx + 1) % len(items)
        return response

    def reset(self, scenario: str | None = None) -> None:
        if scenario is None:
            self._index = {k: 0 for k in self._index}
        else:
            self._index[scenario] = 0


def _make_tool_call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


REGISTRY = CannedRegistry()

REGISTRY.register(
    "happy_path",
    [
        CannedResponse(content="I'll search for France and Germany GDP data and compare them."),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_001", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"Germany GDP 2023"}')],
        ),
        CannedResponse(
            content="France's GDP in 2023 was $3.05 trillion, while Germany's was $4.43 trillion"
            " — a difference of $1.38 trillion.",
        ),
    ],
)

REGISTRY.register(
    "loop",
    [
        CannedResponse(content="I'll search for the GDP data."),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_001", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_003", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="Based on my research, France's GDP in 2023 was approximately $3.05 trillion.",
        ),
    ],
)

REGISTRY.register(
    "risk",
    [
        CannedResponse(
            content="I'll search and send an email report.",
            tool_calls=[_make_tool_call("call_001", "send_email", '{"to":"boss@example.com","subject":"GDP Report"}')],
        ),
        CannedResponse(
            content="",
            tool_calls=[_make_tool_call("call_002", "search", '{"query":"France GDP 2023"}')],
        ),
        CannedResponse(
            content="France's GDP grew by 47% in 2023, reaching $3.05 trillion.",
        ),
    ],
)

_SCIENTIST_RESPONSE = (
    "I propose adding physicochemical descriptors (LogP, TPSA, molecular weight, hydrogen bond "
    "donors/acceptors) alongside the existing Morgan fingerprints. These descriptors capture "
    "global molecular properties that complement the local substructure information in "
    "fingerprints. Literature shows that combining fingerprints with physicochemical features "
    "improves ADMET prediction by 3-8%. For the model, I recommend replacing LogisticRegression "
    "with a Random Forest ensemble (n_estimators=500, max_depth=None), which better handles the "
    "mixed feature space. Expected improvement: 3-5% ROC-AUC gain, reaching approximately 0.92-0.94."
)

_ENGINEER_RESPONSE = (
    "Implementation plan for the proposed changes:\n\n"
    "1. Feature Engineering:\n"
    "   - Import: from rdkit.Chem import Descriptors\n"
    "   - Compute 5 descriptors per molecule: Descriptors.MolLogP(mol), Descriptors.TPSA(mol), "
    "Descriptors.MolWt(mol), Descriptors.NumHDonors(mol), Descriptors.NumHAcceptors(mol)\n"
    "   - Concatenate with Morgan fingerprint vector using numpy.hstack()\n"
    "   - Final feature dimension: 1024 + 5 = 1029\n\n"
    "2. Model Change:\n"
    "   - Replace LogisticRegression with RandomForestClassifier(n_estimators=500, "
    "random_state=42, n_jobs=-1)\n"
    "   - No feature scaling needed (tree-based model)\n\n"
    "3. Potential Pitfalls:\n"
    "   - Feature correlation: LogP and TPSA may correlate. Monitor with VIF.\n"
    "   - Overfitting: 500 trees on 2050 samples. Use cross-validation.\n"
    "   - Data leakage: Ensure descriptors computed only on training split."
)

_EVALUATOR_RESPONSE = (
    "Experiment Assessment:\n\n"
    "Scientific Validity: 4/5 — Adding physicochemical descriptors to fingerprints is "
    "well-established in cheminformatics literature. The choice of LogP, TPSA, MW, HBD, HBA "
    "is standard for ADMET prediction.\n\n"
    "Feasibility: 5/5 — All proposed features are available via RDKit. RandomForest is a "
    "drop-in replacement. Implementation is straightforward.\n\n"
    "Overfitting Risk: 3/5 — 500 trees on 2050 samples is aggressive. Recommend 5-fold CV "
    "and monitoring train/val gap. The 5 additional features are low risk for dimensionality.\n\n"
    "Expected Impact: 4/5 — The 3-5% improvement estimate is realistic based on literature. "
    "Combined fingerprint + descriptor approaches typically see 2-8% gains on molecular "
    "property tasks.\n\n"
    "Final Score: 4.0/5\n"
    "Recommendation: GO — Proceed with implementation. Use 5-fold cross-validation to "
    "validate the improvement before committing."
)

REGISTRY.register(
    "pharma_pipeline",
    [
        CannedResponse(content=_SCIENTIST_RESPONSE),
        CannedResponse(content=_ENGINEER_RESPONSE),
        CannedResponse(content=_EVALUATOR_RESPONSE),
    ],
)
