"""Tests for the canned response registry."""

from __future__ import annotations

import pytest

from agentlens.server.canned import CannedRegistry, CannedResponse


def _make_registry() -> CannedRegistry:
    registry = CannedRegistry()
    registry.register(
        "scenario_a",
        [
            CannedResponse(content="response_1"),
            CannedResponse(content="response_2"),
        ],
    )
    return registry


class TestCannedRegistry:
    def test_registry_next_response_cycles(self) -> None:
        # Arrange
        registry = _make_registry()

        # Act
        r1 = registry.next_response("scenario_a")
        r2 = registry.next_response("scenario_a")
        r3 = registry.next_response("scenario_a")

        # Assert — 3rd call wraps back to first
        assert r1.content == "response_1"
        assert r2.content == "response_2"
        assert r3.content == "response_1"

    def test_registry_reset_resets_index(self) -> None:
        # Arrange
        registry = _make_registry()
        registry.next_response("scenario_a")
        registry.next_response("scenario_a")

        # Act
        registry.reset("scenario_a")
        r = registry.next_response("scenario_a")

        # Assert — after reset, we're back at index 0
        assert r.content == "response_1"

    def test_registry_unknown_scenario_raises(self) -> None:
        # Arrange
        registry = _make_registry()

        # Act & Assert
        with pytest.raises(KeyError):
            registry.next_response("nonexistent_scenario")

    def test_builtin_scenarios_registered(self) -> None:
        # Arrange — import the module-level REGISTRY singleton
        from agentlens.server.canned import REGISTRY

        # Act & Assert — all four built-in scenarios are present
        assert "happy_path" in REGISTRY.responses
        assert "loop" in REGISTRY.responses
        assert "risk" in REGISTRY.responses
        assert "pharma_pipeline" in REGISTRY.responses
