"""Tests for deterministic event field extraction."""

import asyncio

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.strategies import (
    EventFieldStrategy,
    RequiredEventNotFoundError,
    RequiredFieldNotFoundError,
    StrategyMetadata,
)


def create_strategy() -> EventFieldStrategy:
    return EventFieldStrategy(
        metadata=StrategyMetadata(
            name="Extract customer message",
            description="Extract the message from the latest customer event.",
        ),
        event_type="customer.message.received",
        field_name="message",
        output_event_type="customer.message.extracted",
    )


def test_strategy_extracts_field_from_latest_matching_event() -> None:
    older_event = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "My first question."},
        producer="test-suite",
    )
    latest_event = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="test-suite",
        confidence=0.95,
    )

    context = Context(events=(older_event, latest_event))
    strategy = create_strategy()

    outcome = asyncio.run(strategy.run(context))

    assert outcome.output == "I was charged twice."


def test_strategy_emits_derived_event_with_provenance() -> None:
    source_event = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="test-suite",
        provenance="support-case-123",
        confidence=0.95,
    )
    strategy = create_strategy()

    outcome = asyncio.run(strategy.run(Context(events=(source_event,))))

    assert len(outcome.events) == 1

    derived_event = outcome.events[0]

    assert derived_event.event_type == "customer.message.extracted"
    assert derived_event.payload["value"] == "I was charged twice."
    assert derived_event.payload["source_event_id"] == str(source_event.id)
    assert derived_event.provenance == str(source_event.id)
    assert derived_event.confidence == 0.95


def test_strategy_fails_when_required_event_is_missing() -> None:
    strategy = create_strategy()

    with pytest.raises(
        RequiredEventNotFoundError,
        match="customer.message.received",
    ):
        asyncio.run(strategy.run(Context()))


def test_strategy_fails_when_required_field_is_missing() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"subject": "Billing problem"},
                producer="test-suite",
            ),
        )
    )
    strategy = create_strategy()

    with pytest.raises(
        RequiredFieldNotFoundError,
        match="message",
    ):
        asyncio.run(strategy.run(context))
