"""Tests for event-backed context models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from azathoth.context import Context, ContextEvent


def test_append_returns_new_context() -> None:
    original = Context()
    event = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="test-suite",
    )

    updated = original.append(event)

    assert original.events == ()
    assert updated.events == (event,)


def test_context_preserves_event_order() -> None:
    first = ContextEvent(
        event_type="customer.message.received",
        payload={"message": "I was charged twice."},
        producer="test-suite",
        occurred_at=datetime(2026, 7, 28, 14, 0, tzinfo=UTC),
    )
    second = ContextEvent(
        event_type="customer.intent.classified",
        payload={"intent": "duplicate_charge"},
        producer="intent-classifier",
        confidence=0.94,
        occurred_at=datetime(2026, 7, 28, 14, 1, tzinfo=UTC),
    )

    context = Context().append(first).append(second)

    assert context.events == (first, second)


def test_context_can_find_events_by_type() -> None:
    first_classification = ContextEvent(
        event_type="customer.intent.classified",
        payload={"intent": "billing"},
        producer="classifier-v1",
        confidence=0.71,
    )
    unrelated_event = ContextEvent(
        event_type="customer.account.loaded",
        payload={"customer_tier": "enterprise"},
        producer="crm",
    )
    second_classification = ContextEvent(
        event_type="customer.intent.classified",
        payload={"intent": "duplicate_charge"},
        producer="classifier-v2",
        confidence=0.94,
    )

    context = (
        Context().append(first_classification).append(unrelated_event).append(second_classification)
    )

    assert context.by_type("customer.intent.classified") == (
        first_classification,
        second_classification,
    )
    assert context.latest("customer.intent.classified") == second_classification
    assert context.latest("missing.event") is None


def test_context_event_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ContextEvent(
            event_type="customer.intent.classified",
            payload={"intent": "billing"},
            producer="classifier",
            confidence=1.25,
        )
