"""Tests for shared strategy domain models."""

import pytest
from pydantic import ValidationError

from azathoth.context import ContextEvent
from azathoth.strategies import StrategyExecutionMetrics, StrategyMetadata, StrategyOutcome


def test_strategy_metadata_is_immutable() -> None:
    metadata = StrategyMetadata(
        name="Extract latest message",
        description="Extract a field from the latest matching context event.",
    )

    with pytest.raises(ValidationError):
        metadata.name = "Changed name"


def test_strategy_outcome_can_include_context_events() -> None:
    event = ContextEvent(
        event_type="customer.intent.extracted",
        payload={"intent": "duplicate_charge"},
        producer="intent-extraction-strategy",
        confidence=1.0,
    )

    outcome = StrategyOutcome(
        output="duplicate_charge",
        events=(event,),
    )

    assert outcome.output == "duplicate_charge"
    assert outcome.events == (event,)


def test_strategy_outcome_can_include_execution_metrics() -> None:
    metrics = StrategyExecutionMetrics(
        provider="test-provider",
        model="test-model",
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        latency_ms=15,
        estimated_cost_usd=0.0001,
    )

    outcome = StrategyOutcome(
        output="duplicate_charge",
        metrics=metrics,
    )

    assert outcome.metrics == metrics


def test_strategy_execution_metrics_reject_negative_values() -> None:
    with pytest.raises(ValidationError):
        StrategyExecutionMetrics(
            latency_ms=-1,
        )

    with pytest.raises(ValidationError):
        StrategyExecutionMetrics(
            estimated_cost_usd=-0.01,
        )


def test_strategy_execution_metrics_reject_inconsistent_token_total() -> None:
    with pytest.raises(
        ValidationError,
        match="Total tokens must equal",
    ):
        StrategyExecutionMetrics(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=99,
        )
