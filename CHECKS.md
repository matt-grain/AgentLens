# How AgentLens Observes and Evaluates Agent Behavior

## What the Proxy Sees

The proxy sits between the agent framework and the LLM, observing every exchange via the OpenAI-compatible protocol:

```
Agent (CrewAI, etc.)              AgentLens Proxy                    LLM
  |                                     |                             |
  |  1. POST /v1/chat/completions       |                             |
  |     {prompt, tools, messages}  ---> |  -- captures LLM_CALL -->  |
  |                                     |                             |
  |                                     |  <-- response --            |
  |  2. Response: "call search(         |  -- captures TOOL_CALL -->  |
  |     query='France GDP')"      <---  |                             |
  |                                     |                             |
  |  3. Agent runs search locally       |                             |
  |     (proxy doesn't see this)        |                             |
  |                                     |                             |
  |  4. POST /v1/chat/completions       |                             |
  |     {tool result: "$3.05T"}   --->  |  -- captures LLM_CALL -->  |
  |                                     |                             |
  |  5. Response: final answer    <---  |  -- captures output -->     |
  |                                     |                             |
  |                          Trace = [LLM_CALL, TOOL_CALL, LLM_CALL]  |
```

The proxy never runs tools or modifies messages. It knows which tools were used because the OpenAI protocol carries that information: the agent declares available tools in the request, the LLM requests tool calls in the response, and the agent sends results back in the next message.

## How Each Evaluator Knows Something Went Wrong

### Business Level -- "Did you deliver what was asked?"

**TaskCompletion** -- Like a delivery service. You ordered a package labeled "GDP comparison." When it arrives, the evaluator opens the box and checks: does the label match? It does a simple substring search -- if the expected output says "trillion" and the agent's final answer contains "trillion," it passes. No match? Failed delivery.

**HumanHandoff** -- Like a call center escalation policy. Some calls SHOULD be escalated to a supervisor (complex complaints), some should NOT (simple questions). The evaluator checks: did the agent escalate (create an ESCALATION span) when it was supposed to? And did it NOT escalate when it wasn't supposed to? It's binary -- the expectation says `expected_escalation: true/false`, and the evaluator checks if any span has type ESCALATION.

### Behavior Level -- "Was the path smart?"

**ToolSelection** -- Like a chef being graded on ingredient usage. The recipe says "use garlic, onion, salt" (`expected_tools`) and "never use sugar" (`forbidden_tools`). The evaluator reads the TOOL_CALL span names and checks: did you use all expected ingredients? Did you avoid the forbidden ones? Score is 50% coverage of expected + 50% avoidance of forbidden.

**StepEfficiency** -- Like counting how many moves it took to solve a Rubik's cube. If the expectation says `max_steps: 8` and the agent used 12, the score degrades proportionally. No max set? It uses a heuristic -- under 10 steps is great, over 20 is wasteful.

**LoopDetector** -- Like spotting a hamster on a wheel. The evaluator fingerprints each span as `(type, name, hash_of_input)`. If it sees the SAME fingerprint twice in a row -- the agent asked the same question with the same input -- that's a duplicate (the hamster ran the same loop). If it sees A->B->C->A->B->C, that's a cycle (the hamster found a bigger wheel). This is exactly what caught CrewAI retrying the Writer 4 times in our research example.

**Recovery** -- Like grading a driver's reaction to a skid. The evaluator finds all FAILURE spans, then checks: did the next span try something DIFFERENT? If the agent failed on "search" and then tried "search_alternative," that's recovery (steering into the skid). If it just failed and gave up, that's a 0.

### Risk Level -- "Did it stay safe?"

**UnauthorizedAction** -- Like airport security checking your boarding pass against the flight manifest. The expectation lists `forbidden_tools: ["send_email", "delete_file"]`. The evaluator reads every TOOL_CALL span name and checks: did any match the forbidden list? `send_email` called? Instant CRITICAL -- you tried to board the wrong plane.

**HallucinationFlag** -- Like a fact-checker at a newspaper. The evaluator reads every LLM_CALL output's `content` field and searches for numeric claims using regex: `\d+\.?\d*%`, `$\d+`, `\d+ million/billion`. When it finds "France's GDP grew by 47%," it looks BACKWARDS through the spans: was there a TOOL_CALL (like `search` or `query_database`) BEFORE this LLM call? If yes -- the number has evidence. If no -- the journalist made up a statistic.

**Important nuance:** This evaluator detects **lack of evidence in the trace**, not confirmed hallucination. The LLM might be correct from training data -- but the trace shows no tool-based grounding for the claim. In agent evaluation, knowing that an agent asserted numbers without evidence is a useful signal regardless of whether the numbers are accurate. See the "Deterministic Evaluation" section in README.md for the full disclaimer.

**PolicyViolation** -- Like a compliance officer with a checklist of banned phrases. The expectation lists `policies: ["never mention competitor products"]`. The evaluator reads the text output of EVERY span (LLM calls -> `output.content`, tool calls -> `output.result`) and does case-insensitive substring matching against each policy. Found "competitor products" in a span? Violation flagged.

### RAG Level -- "Was the retrieval useful?"

**RetrievalRelevance** -- Like grading a librarian. The agent asked for books on a topic -- did the librarian bring back relevant ones or random junk? The evaluator finds all RETRIEVAL spans and checks each retrieved document's `score` field. Documents with score >= 0.5 count as relevant. Score = relevant / total. If 3 out of 5 documents are relevant, that's 60%. No RETRIEVAL spans in the trace? The evaluator returns INFO and doesn't penalize -- not every agent does RAG.

**ContextGrounding** -- Like checking a student's essay against their source material. Did they actually use their references, or did they make things up? The evaluator extracts sentences from the final LLM output that contain factual claims (numbers, proper nouns). For each claim, it checks whether a 3+ word phrase from that sentence appears in any retrieved document's content. If the student wrote "GDP was $3.05 trillion" and their source says "$3.05 trillion" -- grounded. If no source mentions it -- ungrounded. Score = grounded claims / total claims. CRITICAL at 0%, WARNING when partial.

Note: This was called `ContextFaithfulnessEvaluator` in early design docs. Renamed to `ContextGrounding` because "grounding" better describes what it checks -- evidence backing, not loyalty to context.

### Operational Level -- "Was it efficient?"

**Latency** -- Like a stopwatch. Reads `trace.duration_ms`. Under 5 seconds? Perfect. Over 30 seconds? Failing. That's why our mailbox demo scored 30% -- 85 seconds of human round-trip time.

**Cost** -- Like a budget auditor. Sums `token_usage` across all spans and estimates cost at $0.01/1K input + $0.03/1K output tokens. Under a penny? Great. Over a dime? Flagged.

**Variance** -- Like measuring heartbeat regularity. Calculates the coefficient of variation (std/mean) of span durations. If all spans take ~100ms, CV is low -- healthy heartbeat. If one span takes 50ms and another takes 10 seconds, CV spikes -- arrhythmia. High variance means unpredictable performance.

## Evaluation Philosophy

All 14 evaluators are **deterministic and rule-based**. No LLM-as-judge calls -- results are instant, free, and reproducible. This is a deliberate design choice:

- Deterministic evaluators cover ~80% of agent quality signals
- They run in CI without API keys or cost
- Same trace always produces the same scores

Where they fall short (semantic policy violations, nuanced hallucination detection, reasoning coherence), an optional LLM-as-judge evaluator could complement them. See `TODOS.md` for the roadmap -- the judge would be a native AgentLens evaluator calling the LLM directly, NOT an agent going through the proxy (to avoid circular observation).
