"""Tests for the label a run's input was given, and how lineage carries it (ADR 0123)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import (
    INPUT_SENSITIVITY_EVENT_TYPE,
    SENSITIVITY_PAYLOAD_KEY,
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
    WorkflowLineage,
    child_lineage,
    context_sensitivity,
    create_input_sensitivity_event,
    create_lineage_event,
    decode_step_lineage,
    encode_step_lineage,
    input_sensitivities,
    run_lineage,
)
from azathoth.sensitivity import Sensitivity

WORKFLOW_ID = UUID("51000000-0000-4000-8000-000000000001")
RUN_ID = UUID("51000000-0000-4000-8000-000000000002")
STEP_ID = UUID("51000000-0000-4000-8000-000000000003")

ROOT = LineageRun(
    workflow_id=UUID("61000000-0000-4000-8000-000000000001"),
    run_id=UUID("61000000-0000-4000-8000-000000000002"),
)

OCCURRED = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def parent(
    sensitivity: Sensitivity | None = None,
) -> StepLineage:
    return StepLineage(
        step=LineageStep(
            workflow_id=UUID("71000000-0000-4000-8000-000000000001"),
            run_id=UUID("71000000-0000-4000-8000-000000000002"),
            step_id=UUID("71000000-0000-4000-8000-000000000003"),
            attempt=1,
        ),
        depth=1,
        root=ROOT,
        sensitivity=sensitivity,
    )


def labelled(
    *labels: Sensitivity,
    lineage: StepLineage | None = None,
) -> Context:
    """Return a context whose input was given these labels, under this parent."""

    return Context(
        events=(
            *(create_input_sensitivity_event(label, producer="test") for label in labels),
            *(
                (create_lineage_event(child_lineage(lineage, workflow_id=WORKFLOW_ID)),)
                if lineage is not None
                else ()
            ),
        )
    )


def labelled_with(
    value: JsonValue,
) -> Context:
    """Return a context whose one label event holds this value, or nothing when it is None."""

    payload: dict[str, JsonValue] = {} if value is None else {SENSITIVITY_PAYLOAD_KEY: value}

    return Context(
        events=(
            ContextEvent(
                event_type=INPUT_SENSITIVITY_EVENT_TYPE,
                payload=payload,
                producer="test",
            ),
        )
    )


# The event


def test_the_event_type_and_payload_key_are_named() -> None:
    assert INPUT_SENSITIVITY_EVENT_TYPE == "workflow.input.sensitivity"
    assert SENSITIVITY_PAYLOAD_KEY == "sensitivity"


def test_the_event_records_the_label() -> None:
    event = create_input_sensitivity_event(
        Sensitivity.RESTRICTED,
        producer="azathoth.test",
        occurred_at=OCCURRED,
    )

    assert event.event_type == "workflow.input.sensitivity"
    assert event.payload == {"sensitivity": "restricted"}
    assert event.producer == "azathoth.test"
    assert event.occurred_at == OCCURRED


def test_the_event_occurs_now_by_default() -> None:
    before = datetime.now(UTC)
    event = create_input_sensitivity_event(Sensitivity.PUBLIC, producer="test")

    assert before <= event.occurred_at <= datetime.now(UTC)


def test_a_contexts_input_labels_are_read_in_order() -> None:
    assert input_sensitivities(labelled(Sensitivity.PUBLIC, Sensitivity.RESTRICTED)) == (
        Sensitivity.PUBLIC,
        Sensitivity.RESTRICTED,
    )
    assert input_sensitivities(Context()) == ()


@pytest.mark.parametrize("value", ["secret", None, 3])
def test_an_unknown_label_is_refused(
    value: JsonValue,
) -> None:
    with pytest.raises(ValueError) as caught:
        input_sensitivities(labelled_with(value))

    assert str(caught.value) == (
        f"A workflow.input.sensitivity event holds no label Azathoth knows: {value!r}."
    )


# A run's label


def test_a_run_labelled_by_nothing_is_internal() -> None:
    assert context_sensitivity(Context()) is Sensitivity.INTERNAL


@pytest.mark.parametrize("label", list(Sensitivity))
def test_a_run_takes_its_inputs_label(
    label: Sensitivity,
) -> None:
    assert context_sensitivity(labelled(label)) is label


def test_a_run_takes_its_parents_label() -> None:
    assert context_sensitivity(labelled(lineage=parent(Sensitivity.RESTRICTED))) is (
        Sensitivity.RESTRICTED
    )


def test_a_child_is_never_less_sensitive_than_its_parent() -> None:
    assert context_sensitivity(
        labelled(Sensitivity.PUBLIC, lineage=parent(Sensitivity.RESTRICTED))
    ) is (Sensitivity.RESTRICTED)


def test_a_child_may_be_more_sensitive_than_its_parent() -> None:
    assert context_sensitivity(
        labelled(Sensitivity.RESTRICTED, lineage=parent(Sensitivity.PUBLIC))
    ) is (Sensitivity.RESTRICTED)


def test_an_internal_parent_leaves_an_unlabelled_child_internal() -> None:
    assert context_sensitivity(labelled(lineage=parent())) is Sensitivity.INTERNAL


def test_the_most_sensitive_input_label_wins() -> None:
    assert context_sensitivity(labelled(Sensitivity.RESTRICTED, Sensitivity.PUBLIC)) is (
        Sensitivity.RESTRICTED
    )


# Lineage carries it


def test_a_runs_lineage_carries_a_label_that_is_not_internal() -> None:
    lineage = run_lineage(labelled(Sensitivity.RESTRICTED), workflow_id=WORKFLOW_ID, run_id=RUN_ID)

    assert lineage.sensitivity is Sensitivity.RESTRICTED
    assert lineage.step(step_id=STEP_ID, attempt=1).sensitivity is Sensitivity.RESTRICTED


def test_a_public_runs_lineage_carries_its_label() -> None:
    lineage = run_lineage(labelled(Sensitivity.PUBLIC), workflow_id=WORKFLOW_ID, run_id=RUN_ID)

    assert lineage.sensitivity is Sensitivity.PUBLIC


@pytest.mark.parametrize(
    "context",
    [Context(), labelled(Sensitivity.INTERNAL)],
    ids=["unlabelled", "labelled-internal"],
)
def test_an_internal_runs_lineage_carries_no_label(
    context: Context,
) -> None:
    lineage = run_lineage(context, workflow_id=WORKFLOW_ID, run_id=RUN_ID)

    assert lineage.sensitivity is None
    assert lineage.step(step_id=STEP_ID, attempt=1).sensitivity is None


def test_a_child_runs_lineage_carries_its_parents_label() -> None:
    lineage = run_lineage(
        labelled(lineage=parent(Sensitivity.RESTRICTED)),
        workflow_id=WORKFLOW_ID,
        run_id=RUN_ID,
    )

    assert (lineage.depth, lineage.root, lineage.sensitivity) == (
        2,
        ROOT,
        Sensitivity.RESTRICTED,
    )


def test_a_childs_lineage_takes_the_steps_label() -> None:
    assert child_lineage(parent(Sensitivity.RESTRICTED), workflow_id=WORKFLOW_ID).sensitivity is (
        Sensitivity.RESTRICTED
    )
    assert child_lineage(parent(), workflow_id=WORKFLOW_ID).sensitivity is None


def test_a_labelled_steps_lineage_survives_encoding() -> None:
    step = parent(Sensitivity.RESTRICTED)

    assert json.loads(encode_step_lineage(step))["sensitivity"] == "restricted"
    assert decode_step_lineage(encode_step_lineage(step)) == step


def test_an_unlabelled_lineage_dumps_as_it_did_before_labels() -> None:
    assert "sensitivity" not in json.loads(encode_step_lineage(parent()))
    assert (
        "sensitivity"
        not in create_lineage_event(child_lineage(parent(), workflow_id=WORKFLOW_ID)).payload
    )


def test_a_labelled_childs_lineage_event_records_the_label() -> None:
    event = create_lineage_event(
        child_lineage(parent(Sensitivity.RESTRICTED), workflow_id=WORKFLOW_ID)
    )

    assert event.payload["sensitivity"] == "restricted"
    assert WorkflowLineage.model_validate(event.payload).sensitivity is Sensitivity.RESTRICTED


def test_the_documented_refusal_is_the_one_given() -> None:
    readme = Path(__file__).parents[2] / "src" / "azathoth" / "context" / "README.md"

    with pytest.raises(ValueError) as caught:
        input_sensitivities(labelled_with("secret"))

    assert f"\n{caught.value}\n" in readme.read_text(encoding="utf-8")
