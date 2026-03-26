# Mailbox Brain Integration

## What This Does

The mailbox pattern decouples agent execution from LLM response generation. Any agent
framework calls the proxy as usual (`POST /v1/chat/completions`), but instead of
returning a canned or forwarded response immediately, the proxy queues the request and
blocks. An external "brain" — a script, Claude Code, or a human with curl — polls
`GET /mailbox`, reads the pending request, reasons about the best answer, and submits
it via `POST /mailbox/{id}`. The proxy then unblocks, returns the response to the
agent, and captures the full exchange as a structured trace ready for evaluation.

## Architecture Diagram

```
Agent (CrewAI, etc.)          AgentLens Proxy             Brain (Claude Code, curl, script)
       |                           |                              |
       |  POST /v1/chat/completions|                              |
       |-------------------------->| queues request, blocks        |
       |                           |                              |
       |                           |  GET /mailbox                |
       |                           |<-----------------------------|
       |                           |  returns pending request     |
       |                           |----------------------------->|
       |                           |                              |
       |                           |  POST /mailbox/{id}          |
       |                           |<-----------------------------| submits response
       |  response returned        |                              |
       |<--------------------------|  unblocks, captures trace    |
```

## Quick Start with curl

Open three terminals.

**Terminal 1** — start the proxy in mailbox mode:

```bash
uv run agentlens serve --mode mailbox
```

**Terminal 2** — send a request (this blocks until a brain responds):

```bash
curl -s -X POST http://localhost:8650/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"What is the GDP of France?"}]}'
```

**Terminal 3** — act as the brain:

```bash
# See what is pending
curl -s http://localhost:8650/mailbox

# Read the full request (replace 1 with the id shown above)
curl -s http://localhost:8650/mailbox/1

# Submit a response — Terminal 2 will unblock immediately
curl -s -X POST http://localhost:8650/mailbox/1 \
  -H "Content-Type: application/json" \
  -d '{"response":"France GDP in 2023 was $3.05 trillion."}'
```

## Using the Brain Script

The `brain.py` script automates the poll-and-respond loop:

```bash
# Terminal 1
uv run agentlens serve --mode mailbox

# Terminal 2
uv run python examples/mailbox_brain/brain.py

# Terminal 3 (or run a full agent)
curl -X POST http://localhost:8650/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"Hello"}]}'
```

Options:

```
--url            Proxy base URL  (default: http://localhost:8650)
--idle-timeout   Seconds to wait with no requests before exiting  (default: 30)
--verbose        Print full request details
```

## Using Claude Code as the Brain

Start the proxy, then give Claude Code this prompt:

```
Poll http://localhost:8650/mailbox for pending requests every 2 seconds.
For each request, read GET /mailbox/{id} to see the full messages and tools.
Reason about the best response, then submit via POST /mailbox/{id}.
Keep polling until no requests arrive for 30 seconds.
```

Claude Code will handle each LLM call in the agent trajectory with genuine reasoning,
while AgentLens captures the full trace for evaluation.

## With CrewAI

See `examples/crewai_research/` for the full CrewAI example. To use mailbox mode
instead of mock responses, follow the steps in the
[Using with Mailbox Mode](../crewai_research/README.md#using-with-mailbox-mode) section
of that README.

## Evaluating Traces

After a run, fetch and evaluate captured traces:

```bash
# View all captured traces
curl http://localhost:8650/traces

# Reset traces between runs
curl -X POST http://localhost:8650/traces/reset
```
