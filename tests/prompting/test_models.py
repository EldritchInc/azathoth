"""Tests for context-aware prompt template models."""

import pytest

from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    PromptBinding,
    PromptBindingEventNotFoundError,
    PromptBindingFieldNotFoundError,
    PromptTemplate,
)


def create_template() -> PromptTemplate:
    """Create a deterministic support-classification template."""

    return PromptTemplate(
        text=("Classify this support message:\n\n{customer_message}\n\nReturn only the category."),
        bindings=(
            PromptBinding(
                variable_name="customer_message",
                event_type="customer.message.received",
                field_name="message",
            ),
        ),
    )


def test_template_renders_value_from_latest_matching_event() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "My first question."},
                producer="test-suite",
            ),
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="test-suite",
            ),
        )
    )

    prompt = create_template().render(context)

    assert prompt.text == (
        "Classify this support message:\n\nI was charged twice.\n\nReturn only the category."
    )


def test_template_can_render_multiple_context_bindings() -> None:
    template = PromptTemplate(
        text=("Customer tier: {customer_tier}\nMessage: {customer_message}"),
        bindings=(
            PromptBinding(
                variable_name="customer_tier",
                event_type="customer.account.loaded",
                field_name="tier",
            ),
            PromptBinding(
                variable_name="customer_message",
                event_type="customer.message.received",
                field_name="message",
            ),
        ),
    )

    context = Context(
        events=(
            ContextEvent(
                event_type="customer.account.loaded",
                payload={"tier": "enterprise"},
                producer="crm",
            ),
            ContextEvent(
                event_type="customer.message.received",
                payload={"message": "I was charged twice."},
                producer="support-api",
            ),
        )
    )

    prompt = template.render(context)

    assert prompt.text == ("Customer tier: enterprise\nMessage: I was charged twice.")


def test_template_rejects_missing_required_event() -> None:
    with pytest.raises(
        PromptBindingEventNotFoundError,
        match="customer.message.received",
    ):
        create_template().render(Context())


def test_template_rejects_missing_required_field() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="customer.message.received",
                payload={"subject": "Billing problem"},
                producer="test-suite",
            ),
        )
    )

    with pytest.raises(
        PromptBindingFieldNotFoundError,
        match="message",
    ):
        create_template().render(context)


def test_template_without_bindings_renders_static_text() -> None:
    template = PromptTemplate(
        text="Return the constant category.",
    )

    prompt = template.render(Context())

    assert prompt.text == "Return the constant category."


def test_prompt_template_round_trips_through_json() -> None:
    template = create_template()

    restored = PromptTemplate.model_validate_json(template.model_dump_json())

    assert restored == template
