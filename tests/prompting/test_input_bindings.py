"""Tests for prompt variables bound to workflow step inputs by name."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    PromptBinding,
    PromptBindingInputNotFoundError,
    PromptInputBinding,
    PromptTemplate,
)

BOUND_INPUT_EVENT_TYPE = "workflow.input.bound"


def bound_input(
    name: str,
    value: JsonValue,
) -> ContextEvent:
    """Create the event the workflow runner records for one bound step input."""

    return ContextEvent(
        event_type=BOUND_INPUT_EVENT_TYPE,
        payload={
            "name": name,
            "value": value,
            "producer_step_id": "00000000-0000-4000-8000-000000000001",
            "source_name": name,
        },
        producer="workflow-runner",
    )


def input_template(
    text: str,
    *names: str,
) -> PromptTemplate:
    """Create a template binding each named variable to the step input of that name."""

    return PromptTemplate(
        text=text,
        bindings=tuple(
            PromptInputBinding(
                variable_name=name,
                input_name=name,
            )
            for name in names
        ),
    )


def test_input_binding_renders_the_bound_input_with_its_name() -> None:
    context = Context(
        events=(
            bound_input("plan", "Three acts."),
            bound_input("notes", "The lighthouse keeper lied."),
        )
    )

    prompt = input_template("Plan: {plan}\nNotes: {notes}", "plan", "notes").render(context)

    assert prompt.text == "Plan: Three acts.\nNotes: The lighthouse keeper lied."


def test_input_binding_uses_the_latest_bound_input_with_its_name() -> None:
    context = Context(
        events=(
            bound_input("notes", "Earlier step's notes."),
            bound_input("plan", "Three acts."),
            bound_input("notes", "This step's notes."),
        )
    )

    prompt = input_template("{notes}", "notes").render(context)

    assert prompt.text == "This step's notes."


def test_input_binding_variable_may_differ_from_its_input_name() -> None:
    template = PromptTemplate(
        text="Outline: {outline}",
        bindings=(
            PromptInputBinding(
                variable_name="outline",
                input_name="plan",
            ),
        ),
    )

    prompt = template.render(Context(events=(bound_input("plan", "Three acts."),)))

    assert prompt.text == "Outline: Three acts."


def test_input_binding_rejects_a_missing_input() -> None:
    context = Context(events=(bound_input("plan", "Three acts."),))

    with pytest.raises(PromptBindingInputNotFoundError) as raised:
        input_template("{notes}", "notes").render(context)

    assert str(raised.value) == "No bound workflow input named 'notes' for prompt variable 'notes'."


@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        pytest.param(
            {"title": "Café", "chapters": 2}, '{"title":"Café","chapters":2}', id="object"
        ),
        pytest.param(["Ada", "Grace"], '["Ada","Grace"]', id="list"),
        pytest.param(True, "true", id="boolean"),
        pytest.param(None, "null", id="null"),
        pytest.param(18, "18", id="integer"),
        pytest.param(0.5, "0.5", id="float"),
        pytest.param("plain — text", "plain — text", id="string"),
    ],
)
def test_input_binding_renders_non_strings_as_json(
    value: JsonValue,
    rendered: str,
) -> None:
    prompt = input_template("{value}", "value").render(
        Context(events=(bound_input("value", value),)),
    )

    assert prompt.text == rendered


def test_event_field_binding_renders_non_strings_as_json() -> None:
    template = PromptTemplate(
        text="Account: {account}",
        bindings=(
            PromptBinding(
                variable_name="account",
                event_type="customer.account.loaded",
                field_name="account",
            ),
        ),
    )

    context = Context(
        events=(
            ContextEvent(
                event_type="customer.account.loaded",
                payload={"account": {"tier": "enterprise", "active": True}},
                producer="crm",
            ),
        )
    )

    assert template.render(context).text == 'Account: {"tier":"enterprise","active":true}'


def test_template_mixes_input_and_event_field_bindings() -> None:
    template = PromptTemplate(
        text="Idea: {idea}\nPlan: {plan}",
        bindings=(
            PromptBinding(
                variable_name="idea",
                event_type="workflow.input.received",
                field_name="input",
            ),
            PromptInputBinding(
                variable_name="plan",
                input_name="plan",
            ),
        ),
    )

    context = Context(
        events=(
            ContextEvent(
                event_type="workflow.input.received",
                payload={"input": "A lighthouse at the end of the world."},
                producer="azathoth.configured",
            ),
            bound_input("plan", "Three acts."),
        )
    )

    assert template.render(context).text == (
        "Idea: A lighthouse at the end of the world.\nPlan: Three acts."
    )


def test_bindings_decode_into_their_own_forms() -> None:
    template = PromptTemplate.model_validate(
        {
            "text": "{idea} {plan}",
            "bindings": [
                {
                    "variable_name": "idea",
                    "event_type": "workflow.input.received",
                    "field_name": "input",
                },
                {
                    "variable_name": "plan",
                    "input_name": "plan",
                },
            ],
        }
    )

    assert template.bindings == (
        PromptBinding(
            variable_name="idea",
            event_type="workflow.input.received",
            field_name="input",
        ),
        PromptInputBinding(
            variable_name="plan",
            input_name="plan",
        ),
    )


def test_a_binding_cannot_mix_both_forms() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate.model_validate(
            {
                "text": "{plan}",
                "bindings": [
                    {
                        "variable_name": "plan",
                        "input_name": "plan",
                        "event_type": "workflow.input.received",
                        "field_name": "input",
                    },
                ],
            }
        )


def test_event_field_binding_serializes_unchanged() -> None:
    binding = PromptBinding(
        variable_name="idea",
        event_type="workflow.input.received",
        field_name="input",
    )

    assert binding.model_dump() == {
        "variable_name": "idea",
        "event_type": "workflow.input.received",
        "field_name": "input",
    }
