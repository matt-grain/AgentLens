"""Integration tests for the AgentLens proxy server."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from agentlens.server.proxy import create_app


@pytest.fixture
def test_client() -> TestClient:
    app = create_app(mode="mock", scenario="happy_path")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health & meta endpoints
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_ok(test_client: TestClient) -> None:
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] == "mock"


def test_models_endpoint_returns_model_list(test_client: TestClient) -> None:
    response = test_client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "agentlens-mock"


# ---------------------------------------------------------------------------
# Chat completions
# ---------------------------------------------------------------------------


def test_chat_completions_mock_mode_returns_canned(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "Compare GDP of France and Germany"}],
    }
    response = test_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "usage" in data


def test_chat_completions_creates_span(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "What is the GDP of France?"}],
    }
    test_client.post("/v1/chat/completions", json=payload)
    test_client.post("/traces/reset")

    traces_response = test_client.get("/traces")
    assert traces_response.status_code == 200
    traces = traces_response.json()
    assert len(traces) == 1
    assert len(traces[0]["spans"]) >= 1
    assert traces[0]["spans"][0]["span_type"] == "llm_call"


def test_chat_completions_with_tool_calls_creates_tool_spans(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "Compare France and Germany GDP"}],
    }
    # happy_path response[0] is a plan (no tool calls), response[1] has a tool call
    test_client.post("/v1/chat/completions", json=payload)
    test_client.post("/v1/chat/completions", json=payload)
    test_client.post("/traces/reset")

    traces = test_client.get("/traces").json()
    assert len(traces) == 1
    span_types = [s["span_type"] for s in traces[0]["spans"]]
    assert "tool_call" in span_types


# ---------------------------------------------------------------------------
# Traces endpoints
# ---------------------------------------------------------------------------


def test_traces_endpoint_returns_captured_traces(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "Research GDP data"}],
    }
    test_client.post("/v1/chat/completions", json=payload)
    test_client.post("/traces/reset")

    response = test_client.get("/traces")
    assert response.status_code == 200
    traces: list[dict[str, object]] = response.json()
    assert len(traces) >= 1
    assert "id" in traces[0]
    assert "task" in traces[0]
    assert "spans" in traces[0]


def test_traces_reset_clears_current_spans_and_finalizes(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "task one"}],
    }
    test_client.post("/v1/chat/completions", json=payload)

    reset_response = test_client.post("/traces/reset")
    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "reset"

    # A second reset with no new spans should not add another trace
    test_client.post("/traces/reset")
    traces = test_client.get("/traces").json()
    assert len(traces) == 1


def test_get_trace_by_id_returns_correct_trace(test_client: TestClient) -> None:
    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "specific task"}],
    }
    test_client.post("/v1/chat/completions", json=payload)
    test_client.post("/traces/reset")

    traces = test_client.get("/traces").json()
    trace_id = traces[0]["id"]

    response = test_client.get(f"/traces/{trace_id}")
    assert response.status_code == 200
    assert response.json()["id"] == trace_id


def test_get_trace_unknown_id_returns_404(test_client: TestClient) -> None:
    response = test_client.get("/traces/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Scenario switching
# ---------------------------------------------------------------------------


def test_scenario_switch_changes_responses(test_client: TestClient) -> None:
    # Switch to "risk" scenario
    switch_response = test_client.post("/scenario/risk")
    assert switch_response.status_code == 200
    assert switch_response.json()["scenario"] == "risk"

    payload = {
        "model": "agentlens-mock",
        "messages": [{"role": "user", "content": "test task"}],
    }
    response = test_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    # risk scenario first response has a tool call (send_email)
    assert data["choices"][0]["message"].get("tool_calls") is not None
