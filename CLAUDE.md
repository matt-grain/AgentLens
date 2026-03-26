# AgentLens

Trajectory-first agent evaluation framework.

## Tech Stack
- Python 3.13, uv
- Pydantic 2.x for models
- FastAPI for proxy server
- Rich for terminal output
- Typer for CLI

## Architecture
- `src/agentlens/models/` — Pydantic models (Trace, Span, EvalResult, etc.)
- `src/agentlens/server/` — OpenAI-compatible proxy server
- `src/agentlens/evaluators/` — Pluggable evaluators (12 total)
- `src/agentlens/report/` — Terminal and HTML report generators
- `src/agentlens/cli.py` — Typer CLI entry point
- `demo/` — Research assistant agent and fixtures

## Patterns
- All models are frozen Pydantic BaseModel with `frozen=True`
- Evaluators implement the Evaluator Protocol (name, level, evaluate method)
- No LLM-as-judge — all evaluators are deterministic
- Proxy server auto-captures traces from LLM calls

## Commands
- `uv run agentlens demo` — Run demo with fixtures
- `uv run agentlens serve` — Start proxy server
- `uv run pytest` — Run tests
- `uv run ruff check src/` — Lint
- `uv run pyright .` — Type check
