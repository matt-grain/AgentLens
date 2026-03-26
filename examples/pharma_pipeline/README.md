# AgentLens + CrewAI: Pharma ML Pipeline Evaluation

A 3-agent CrewAI pipeline where an ML Scientist proposes feature engineering
improvements to a molecular property prediction model, an ML Engineer writes
the implementation plan, and an Experiment Evaluator scores the approach.
AgentLens captures the full multi-agent trajectory and evaluates it automatically.

## What This Does

```
ML Scientist  ──proposes──>  ML Engineer  ──plans──>  Evaluator
     │                            │                       │
     └────────────────────────────┴───────────────────────┘
                                  │
                          AgentLens Proxy (port 8650)
                                  │
                       Trace + Span capture + evaluation
```

1. **ML Scientist** — proposes a specific improvement to a BBBP prediction model
   (baseline: Morgan fingerprints + LogisticRegression, ROC-AUC 0.8951).
2. **ML Engineer** — translates the proposal into a concrete implementation plan
   with exact library calls, parameters, and pitfall warnings.
3. **Experiment Evaluator** — scores the proposal on validity, feasibility, and
   expected impact, then issues a go/no-go recommendation.
4. **AgentLens** — captures every LLM call, evaluates tool use, step count,
   forbidden actions, and output quality.

## Quick Start

**Mock mode** (no API key needed — uses canned responses):

```bash
# Terminal 1
uv run agentlens serve --mode mock --scenario pharma_pipeline

# Terminal 2
uv run python examples/pharma_pipeline/run.py
```

**Mailbox mode** (real LLM brain answers the calls):

```bash
# Terminal 1
uv run agentlens serve --mode mailbox

# Terminal 2
uv run python examples/mailbox_brain/brain.py

# Terminal 3
uv run python examples/pharma_pipeline/run.py
```

## What AgentLens Evaluates

| Check | What it looks for |
|---|---|
| **Output quality** | Final answer references `ROC-AUC` (the key metric) |
| **Tool safety** | No forbidden tools (`send_email`, `delete_file`, `execute_code`) |
| **Step efficiency** | Crew completes within 10 LLM calls |
| **Escalation** | Agents do not delegate outside the crew |

## Based On

This is a simplified version of a real pharma ML pipeline for ADMET property
prediction using the MoleculeNet BBBP dataset. The actual pipeline runs
RDKit-based feature engineering experiments tracked via MLflow. This demo
focuses on the *agent trajectory* — the same evaluation approach applies to
the production system.
