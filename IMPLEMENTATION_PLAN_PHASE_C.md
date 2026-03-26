# Phase C: Integration Example

**Dependencies:** Phase B (mailbox endpoints must work)
**Agent:** `general-purpose`

## Overview

Create `examples/mailbox_brain/` showing how to use the mailbox mode with Claude Code or curl as the "brain" that answers requests on behalf of an agent under evaluation. Also update the CrewAI example README to mention mailbox mode.

## Files to Create

### `examples/mailbox_brain/README.md`
**Purpose:** Step-by-step guide for using mailbox mode
**Sections:**
1. **What This Does** — 1 paragraph explaining the mailbox pattern
2. **Architecture Diagram** — ASCII showing Agent → Proxy (mailbox) ← Brain
3. **Quick Start with curl** — 3 terminals:
   - Terminal 1: `uv run agentlens serve --mode mailbox`
   - Terminal 2: `curl -X POST .../v1/chat/completions -d '...'` (simulates an agent)
   - Terminal 3: `curl .../mailbox` → read request → `curl -X POST .../mailbox/1 -d '...'`
4. **Using Claude Code as the Brain** — Prompt template for a Claude Code session:
   ```
   "Poll http://localhost:8650/mailbox for pending requests.
    For each, read GET /mailbox/{id}, reason about the messages,
    then POST /mailbox/{id} with your response.
    Keep polling until idle for 30 seconds."
   ```
5. **With CrewAI** — Reference to `examples/crewai_research/` + note to use `--mode mailbox` instead of `--mode mock`
6. **Evaluating Traces** — After the run: `/traces/reset` → `/traces` → evaluate

### `examples/mailbox_brain/brain.py`
**Purpose:** Automated brain script that polls the mailbox and responds
**Implementation:**
- Uses `httpx` to poll `GET /mailbox` every 1 second
- When a pending request is found, reads `GET /mailbox/{id}`
- Generates a simple response (for demo purposes, just echo the last user message with a prefix "Based on my analysis: ...")
- Submits via `POST /mailbox/{id}`
- Tracks idle time — exits after `--idle-timeout` seconds (default 30) with no new requests
- Prints each request/response pair to stdout

**CLI args (via argparse):**
- `--url`: proxy URL (default: `http://localhost:8650`)
- `--idle-timeout`: seconds to wait before exiting (default: 30)
- `--verbose`: print full request messages

**Constraints:**
- Under 100 lines
- Sync httpx (not async — keeps it simple)
- No AgentLens imports — this is a standalone script that only uses HTTP

### `examples/mailbox_brain/requirements.txt`
```
httpx>=0.27.0
```

## Files to Modify

### `examples/crewai_research/README.md` (MODIFY)
**Change:** Add a "Using with Mailbox Mode" section at the end:
```markdown
## Using with Mailbox Mode

Instead of mock responses, you can use a real LLM brain via the mailbox:

1. Start proxy in mailbox mode: `uv run agentlens serve --mode mailbox`
2. In another terminal, start a brain: `uv run python examples/mailbox_brain/brain.py`
   (or use Claude Code as the brain — see `examples/mailbox_brain/README.md`)
3. Run this script: `uv run python examples/crewai_research/run.py`
```

## Verification

```bash
# Brain script runs without errors (dry run — no server needed for syntax check)
uv run ruff check examples/mailbox_brain/
uv run ruff format examples/mailbox_brain/

# Integration test (manual):
# Terminal 1: uv run agentlens serve --mode mailbox
# Terminal 2: uv run python examples/mailbox_brain/brain.py --idle-timeout 10
# Terminal 3: curl -X POST http://localhost:8650/v1/chat/completions \
#   -H "Content-Type: application/json" \
#   -d '{"model":"test","messages":[{"role":"user","content":"What is the GDP of France?"}]}'
# Verify: Terminal 3 gets a response, Terminal 2 shows the interaction
```
