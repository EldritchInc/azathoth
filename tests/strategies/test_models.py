"""Tests for shared strategy domain models."""

import pytest
from pydantic import ValidationError

from azathoth.context import ContextEvent
from azathoth.strategies import StrategyMetadata, StrategyOutcome


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
