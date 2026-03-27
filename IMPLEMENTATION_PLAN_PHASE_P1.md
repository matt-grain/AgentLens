# Phase P1: Fix Span Timestamps, Token Usage, Agent Identity

**Dependencies:** None
**Agent:** `python-fastapi`

## Overview

Three bugs make the evaluation report look broken in real scenarios:
1. **Span duration shows 0ms** — timestamps set AFTER response, so start_time == end_time
2. **Token usage shows 0in/0out in mailbox mode** — usage hardcoded to 0
3. **No agent identity** — all spans show generic "llm_call" in multi-agent traces

All three fixes center on `collector.py` (span building) and `proxy.py` (timing capture).

---

## Fix 1: Span Timestamps (P1.1)

### Problem
`_build_llm_span` in `collector.py` sets `start_time=now, end_time=now` (lines 42-43). Both timestamps are captured at the same instant AFTER the response is received, so `span.duration_ms` is always 0.

### Fix

**MODIFY `src/agentlens/server/collector.py`:**

1. Change `record_llm_call` signature to accept `start_time: datetime`:
   ```python
   def record_llm_call(
       self,
       messages: list[ChatMessage],
       content: str,
       tool_calls: list[dict[str, Any]],
       usage: dict[str, int],
       start_time: datetime | None = None,
   ) -> None:
   ```

2. Pass `start_time` to `_build_llm_span`. If None, use `_now()` as fallback.

3. Change `_build_llm_span` to accept `start_time: datetime` parameter:
   ```python
   def _build_llm_span(
       messages: list[ChatMessage],
       content: str,
       tool_calls: list[dict[str, Any]],
       usage: dict[str, int],
       llm_span_id: str,
       start_time: datetime,
   ) -> Span:
   ```
   Set `start_time=start_time, end_time=_now()` — now end_time is AFTER start_time.

4. Update `_build_tool_spans` to accept a `start_time: datetime` parameter:
   ```python
   def _build_tool_spans(tool_calls: list[dict[str, Any]], parent_id: str, start_time: datetime) -> list[Span]:
   ```
   Set each tool span's `start_time=start_time, end_time=start_time` (tools are "instant" from the proxy's perspective — it doesn't execute them). In `record_llm_call`, capture end_time after building the LLM span and pass it:
   ```python
   llm_span = _build_llm_span(messages, content, tool_calls, usage, llm_span_id, actual_start)
   self.current_spans.append(llm_span)
   if tool_calls:
       self.current_spans.extend(_build_tool_spans(tool_calls, llm_span_id, llm_span.end_time))
   ```

**MODIFY `src/agentlens/server/proxy.py`:**

5. In `chat_completions`, capture `start_time` BEFORE the mode dispatch. Use `datetime.now(UTC)` directly (already imported in proxy.py — do NOT import private `_now` from collector):
   ```python
   async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:
       request_start = datetime.now(UTC)

       if mode == ServerMode.MOCK:
           ...
       elif mode == ServerMode.MAILBOX:
           ...
       else:
           ...

       collector.record_llm_call(request.messages, content, tool_calls_raw, usage, start_time=request_start)
   ```

### Expected Result
- Demo fixture spans: still 0ms (fixtures have pre-baked timestamps, unchanged)
- Live/mailbox spans: show real wall-clock duration (e.g., 500ms for mock, 30s for mailbox)
- Trajectory timeline: `✓ llm_call (523ms)` instead of `✓ llm_call (0ms)`

---

## Fix 2: Token Usage in Mailbox Mode (P1.2)

### Problem
In mailbox mode, `usage` is hardcoded to `{"prompt_tokens": 0, "completion_tokens": 0}` (proxy.py line 128). The Cost evaluator always scores 100% because cost is $0.

### Fix

**MODIFY `src/agentlens/server/proxy.py`:**

1. In the mailbox branch, estimate tokens from message length:
   ```python
   # Rough estimate: ~4 chars per token (standard heuristic)
   total_input_chars = sum(len(m.content or "") for m in request.messages)
   total_output_chars = len(content)
   usage: dict[str, Any] = {
       "prompt_tokens": max(1, total_input_chars // 4),
       "completion_tokens": max(1, total_output_chars // 4),
   }
   ```

2. In mock mode, the canned responses already have usage defined. No change needed.

3. In proxy mode, usage is already parsed from the upstream response. No change needed.

### Expected Result
- Mailbox mode: estimated token counts based on message length
- Cost evaluator: gives meaningful scores instead of always 100%

---

## Fix 3: Agent Identity per Span (P1.3)

### Problem
All LLM_CALL spans have `name="llm_call"`. In a 3-agent crew, you can't tell which agent made which call. The trajectory shows:
```
✓ llm_call (0ms)
✓ llm_call (0ms)
✓ llm_call (0ms)
```
Instead of:
```
✓ [ML Scientist] llm_call (523ms)
✓ [ML Engineer] llm_call (412ms)
✓ [Evaluator] llm_call (389ms)
```

### Fix

**MODIFY `src/agentlens/server/collector.py`:**

1. Change `record_llm_call` to accept optional `agent_name: str | None = None`:
   ```python
   def record_llm_call(
       self,
       messages: list[ChatMessage],
       content: str,
       tool_calls: list[dict[str, Any]],
       usage: dict[str, int],
       start_time: datetime | None = None,
       agent_name: str | None = None,
   ) -> None:
   ```

2. Pass `agent_name` to `_build_llm_span`. Store it in the span's `metadata` field:
   ```python
   metadata = {}
   if agent_name:
       metadata["agent_name"] = agent_name
   ```

3. Add a helper `_extract_agent_name(messages: list[ChatMessage]) -> str | None` that parses the system message for agent role. CrewAI always includes `"You are {Role}."` as the first sentence of the system message:
   ```python
   def _extract_agent_name(messages: list[ChatMessage]) -> str | None:
       system_msg = next((m for m in messages if m.role == MessageRole.SYSTEM), None)
       if system_msg and system_msg.content:
           # CrewAI format: "You are {Role}. {backstory...}"
           text = system_msg.content
           if text.startswith("You are "):
               # Extract role name up to the first period
               end = text.find(".", 8)
               if end > 8:
                   return text[8:end]
       return None
   ```

4. In `record_llm_call`, if `agent_name` is not provided, try extracting from messages:
   ```python
   if agent_name is None:
       agent_name = _extract_agent_name(messages)
   ```

**MODIFY `src/agentlens/server/proxy.py`:**

5. No changes needed — `collector.record_llm_call` auto-extracts the agent name from the system message.

**MODIFY `src/agentlens/report/terminal.py`:**

6. In `_print_trajectory`, check for `agent_name` in span metadata and display it:
   ```python
   agent = span.metadata.get("agent_name", "")
   agent_prefix = f"[dim][{agent}][/dim] " if agent else ""
   console.print(f"  {icon} {agent_prefix}[bold]{span.name}[/bold]  ({duration}ms)")
   ```

**MODIFY `src/agentlens/report/html.py` or `report/templates/report.html.j2`:**

7. In the trajectory timeline section of `report.html.j2`, show agent name if present in metadata:
   ```html
   {% if span.metadata.get('agent_name') %}
   <span class="agent-name">{{ span.metadata['agent_name'] }}</span>
   {% endif %}
   ```
   Add CSS for `.agent-name`:
   ```css
   .agent-name {
       color: var(--text-tertiary);
       font-size: 0.75rem;
       font-family: var(--mono);
       margin-right: 0.5rem;
   }
   ```

### Expected Result
```
Trajectory Timeline
  ✓ [ML Scientist] llm_call (523ms)
  ✓ [ML Engineer] llm_call (412ms)
  ✓ [Experiment Evaluator] llm_call (389ms)
```

---

## Test Updates

**MODIFY `tests/test_collector.py`:**

Add tests:
- `test_record_llm_call_with_start_time_sets_duration` — Pass a start_time 500ms before now, verify span.duration_ms > 0
- `test_record_llm_call_extracts_agent_name_from_system_message` — Pass messages with system "You are Research Analyst. ...", verify metadata["agent_name"] == "Research Analyst"
- `test_record_llm_call_no_system_message_no_agent_name` — No system message, verify "agent_name" not in metadata
- `test_record_llm_call_estimates_tokens_when_zero` — This is tested via proxy, not collector directly

**MODIFY `tests/test_server.py`:**

No new tests needed — existing tests use mock mode which already provides usage. The timestamp fix doesn't change the API contract.

## Verification

```bash
uv run pytest tests/ -v
uv run pyright src/
uv run ruff check src/ tests/
uv run agentlens demo --verbose  # check durations, token counts
```
