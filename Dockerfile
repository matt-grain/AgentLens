# AgentLens — OTel trajectory-tracing proxy for LLM agent workflows.
#
# Built as part of the pharma-derive (CDDE) Docker Compose stack but usable
# standalone. Serves an OpenAI-compatible endpoint on port 8650 that records
# every request/response as an OTel span to ./traces.
#
# Build:
#     docker build -t agentlens:latest .
#
# Run standalone:
#     docker run --rm -p 8650:8650 -v $(pwd)/traces:/app/traces agentlens:latest
#
# Run in compose (see pharma-derive/docker-compose.yml):
#     services.agentlens.image: agentlens:latest
#
# Multi-stage build mirrors the pharma-derive backend Dockerfile: uv + Python
# 3.13-slim, with dependencies baked into /app/.venv at build time. Runtime
# stage does NOT copy .env — configuration is injected via compose environment.

# Stage 1: builder
FROM python:3.13-slim AS builder
WORKDIR /app

# Install uv (Astral's package manager) — frozen binary copy is faster and
# reproducible compared to `pip install uv`.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies only (no project code yet — maximise Docker layer cache
# hits on unchanged uv.lock).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: runtime
FROM python:3.13-slim
WORKDIR /app

# Bring in the pre-built virtualenv from stage 1.
COPY --from=builder /app/.venv /app/.venv

# Copy only what the CLI needs at runtime. Leave out tests, docs, benchmarks,
# examples — keeps the image small and reviewable.
COPY src/ src/
COPY pyproject.toml ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8650

# Default: serve in mailbox mode on 0.0.0.0:8650 with traces written to
# /app/traces (mount a volume here in compose to persist across restarts).
# The serve command always binds to 0.0.0.0 internally — there is no --host flag.
CMD ["agentlens", "serve", "--mode", "mailbox", "--port", "8650", "--traces-dir", "/app/traces"]
