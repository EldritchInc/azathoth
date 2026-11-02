"""Tests for workflow lineage recorded in a child run's initial context (ADR 0104)."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import (
    LINEAGE_EVENT_TYPE,
    LINEAGE_PRODUCER,
    MAX_WORKFLOW_DEPTH,
    Context,
    ContextEvent,
    LineageError,
    LineageRun,
    LineageStep,
    RunLineage,
    StepLineage,
    WorkflowDepthError,
    WorkflowLineage,
    active_step_lineage,
    child_lineage,
    create_lineage_event,
    decode_step_lineage,
    encode_step_lineage,
    lineage_of,
    run_lineage,
    running_step,
)

ROOT_WORKFLOW_ID = UUID("10000000-0000-4000-8000-000000000001")
ROOT_RUN_ID = UUID("10000000-0000-4000-8000-000000000002")
PARENT_WORKFLOW_ID = UUID("20000000-0000-4000-8000-000000000001")
PARENT_RUN_ID = UUID("20000000-0000-4000-8000-000000000002")
PARENT_STEP_ID = UUID("20000000-0000-4000-8000-000000000003")
CHILD_WORKFLOW_ID = UUID("30000000-0000-4000-8000-000000000001")
CHILD_RUN_ID = UUID("30000000-0000-4000-8000-000000000002")
CHILD_STEP_ID = UUID("30000000-0000-4000-8000-000000000003")

OCCURRED_AT = datetime(2026, 11, 1, 19, 30, tzinfo=UTC)

ROOT = LineageRun(workflow_id=ROOT_WORKFLOW_ID, run_id=ROOT_RUN_ID)

PARENT_STEP = LineageStep(
    workflow_id=PARENT_WORKFLOW_ID,
    run_id=PARENT_RUN_ID,
    step_id=PARENT_STEP_ID,
    attempt=2,
)


def parent_step(
    depth: int,
) -> StepLineage:
    """Return the lineage of the parent step, in a run at the given depth."""

    return StepLineage(step=PARENT_STEP, depth=depth, root=ROOT)


def child_context(
    lineage: WorkflowLineage,
) -> Context:
    """Return a child run's initial context: its input, then its lineage."""

    return Context(
        events=(
            ContextEvent(
                event_type="workflow.input.received",
                payload={"input": {"text": "hello"}},
                producer="test",
            ),
            create_lineage_event(lineage, occurred_at=OCCURRED_AT),
        )
    )


# Child lineage


def test_a_child_of_a_root_step_is_one_level_deep() -> None:
    assert child_lineage(parent_step(0), workflow_id=CHILD_WORKFLOW_ID) == WorkflowLineage(
        depth=1,
        parent=PARENT_STEP,
        root=ROOT,
    )


def test_a_child_keeps_its_parents_root() -> None:
    lineage = child_lineage(parent_step(3), workflow_id=CHILD_WORKFLOW_ID)

    assert lineage.depth == 4
    assert lineage.root == ROOT


def test_a_child_may_run_at_the_depth_limit() -> None:
    lineage = child_lineage(
        parent_step(MAX_WORKFLOW_DEPTH - 1),
        workflow_id=CHILD_WORKFLOW_ID,
    )

    assert lineage.depth == MAX_WORKFLOW_DEPTH == 8


def test_a_child_beyond_the_depth_limit_is_refused() -> None:
    with pytest.raises(WorkflowDepthError) as error:
        child_lineage(parent_step(MAX_WORKFLOW_DEPTH), workflow_id=CHILD_WORKFLOW_ID)

    assert str(error.value) == (
        f"Workflow {CHILD_WORKFLOW_ID} would run at depth 9, "
        "beyond the limit of 8 nested workflows."
    )


# The lineage event


def test_the_lineage_event_records_the_lineage_as_json() -> None:
    lineage = child_lineage(parent_step(0), workflow_id=CHILD_WORKFLOW_ID)

    event = create_lineage_event(lineage, occurred_at=OCCURRED_AT)

    assert event.event_type == LINEAGE_EVENT_TYPE == "workflow.lineage.received"
    assert event.producer == LINEAGE_PRODUCER == "azathoth.lineage"
    assert event.occurred_at == OCCURRED_AT
    assert event.payload == {
        "depth": 1,
        "parent": {
            "workflow_id": str(PARENT_WORKFLOW_ID),
            "run_id": str(PARENT_RUN_ID),
            "step_id": str(PARENT_STEP_ID),
            "attempt": 2,
        },
        "root": {
            "workflow_id": str(ROOT_WORKFLOW_ID),
            "run_id": str(ROOT_RUN_ID),
        },
    }


def test_the_lineage_event_occurs_now_by_default() -> None:
    before = datetime.now(UTC)

    event = create_lineage_event(child_lineage(parent_step(0), workflow_id=CHILD_WORKFLOW_ID))

    assert before <= event.occurred_at <= datetime.now(UTC)


def test_a_root_runs_context_records_no_lineage() -> None:
    assert lineage_of(Context()) is None


def test_a_child_runs_context_records_its_lineage() -> None:
    lineage = child_lineage(parent_step(2), workflow_id=CHILD_WORKFLOW_ID)

    assert lineage_of(child_context(lineage)) == lineage


def test_a_context_with_two_lineage_events_is_rejected() -> None:
    lineage = child_lineage(parent_step(0), workflow_id=CHILD_WORKFLOW_ID)

    context = child_context(lineage).append(create_lineage_event(lineage))

    with pytest.raises(LineageError) as error:
        lineage_of(context)

    assert str(error.value) == "A context records lineage once; this one has 2 events."


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            {"depth": 0, "parent": PARENT_STEP.model_dump(mode="json"), "root": {}},
            "The context's lineage is not valid lineage: depth: Input should be greater "
            "than or equal to 1.",
            id="depth-zero",
        ),
        pytest.param(
            {"depth": 1, "root": ROOT.model_dump(mode="json")},
            "The context's lineage is not valid lineage: parent: Field required.",
            id="no-parent",
        ),
        pytest.param(
            {
                "depth": 1,
                "parent": PARENT_STEP.model_dump(mode="json"),
                "root": ROOT.model_dump(mode="json"),
                "iteration": 3,
            },
            "The context's lineage is not valid lineage: iteration: Extra inputs are not "
            "permitted.",
            id="extra-field",
        ),
    ],
)
def test_a_context_with_invalid_lineage_is_rejected(
    payload: dict[str, object],
    message: str,
) -> None:
    context = Context(
        events=(
            ContextEvent.model_validate(
                {
                    "event_type": LINEAGE_EVENT_TYPE,
                    "payload": payload,
                    "producer": LINEAGE_PRODUCER,
                }
            ),
        )
    )

    with pytest.raises(LineageError) as error:
        lineage_of(context)

    assert str(error.value) == message


# A run's lineage


def test_a_root_run_is_its_own_root_at_depth_zero() -> None:
    assert run_lineage(Context(), workflow_id=ROOT_WORKFLOW_ID, run_id=ROOT_RUN_ID) == (
        RunLineage(run=ROOT, depth=0, root=ROOT)
    )


def test_a_child_run_takes_its_depth_and_root_from_its_context() -> None:
    context = child_context(child_lineage(parent_step(2), workflow_id=CHILD_WORKFLOW_ID))

    lineage = run_lineage(context, workflow_id=CHILD_WORKFLOW_ID, run_id=CHILD_RUN_ID)

    assert lineage == RunLineage(
        run=LineageRun(workflow_id=CHILD_WORKFLOW_ID, run_id=CHILD_RUN_ID),
        depth=3,
        root=ROOT,
    )


def test_a_runs_step_lineage_names_the_step_attempt() -> None:
    context = child_context(child_lineage(parent_step(2), workflow_id=CHILD_WORKFLOW_ID))

    lineage = run_lineage(context, workflow_id=CHILD_WORKFLOW_ID, run_id=CHILD_RUN_ID)

    assert lineage.step(step_id=CHILD_STEP_ID, attempt=1) == StepLineage(
        step=LineageStep(
            workflow_id=CHILD_WORKFLOW_ID,
            run_id=CHILD_RUN_ID,
            step_id=CHILD_STEP_ID,
            attempt=1,
        ),
        depth=3,
        root=ROOT,
    )


def test_a_grandchild_is_one_level_below_its_parent_with_the_same_root() -> None:
    child = run_lineage(
        child_context(child_lineage(parent_step(0), workflow_id=CHILD_WORKFLOW_ID)),
        workflow_id=CHILD_WORKFLOW_ID,
        run_id=CHILD_RUN_ID,
    )

    grandchild = child_lineage(
        child.step(step_id=CHILD_STEP_ID, attempt=1),
        workflow_id=UUID("40000000-0000-4000-8000-000000000001"),
    )

    assert grandchild.depth == 2
    assert grandchild.parent.run_id == CHILD_RUN_ID
    assert grandchild.root == ROOT


# Encoding a step's lineage for a child process


def test_a_steps_lineage_survives_encoding() -> None:
    lineage = parent_step(4)

    assert decode_step_lineage(encode_step_lineage(lineage)) == lineage


def test_an_encoded_steps_lineage_is_compact_json() -> None:
    encoded = encode_step_lineage(parent_step(0))

    assert "\n" not in encoded
    assert json.loads(encoded) == {
        "step": {
            "workflow_id": str(PARENT_WORKFLOW_ID),
            "run_id": str(PARENT_RUN_ID),
            "step_id": str(PARENT_STEP_ID),
            "attempt": 2,
        },
        "depth": 0,
        "root": {"workflow_id": str(ROOT_WORKFLOW_ID), "run_id": str(ROOT_RUN_ID)},
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("not json", "Invalid JSON: ", id="text"),
        pytest.param("{}", "step: Field required", id="empty"),
        pytest.param(
            json.dumps(
                {
                    "step": PARENT_STEP.model_dump(mode="json"),
                    "depth": -1,
                    "root": ROOT.model_dump(mode="json"),
                }
            ),
            "depth: Input should be greater than or equal to 0",
            id="negative-depth",
        ),
        pytest.param(
            json.dumps(
                {
                    "step": {**PARENT_STEP.model_dump(mode="json"), "attempt": 0},
                    "depth": 0,
                    "root": ROOT.model_dump(mode="json"),
                }
            ),
            "step.attempt: Input should be greater than or equal to 1",
            id="attempt-zero",
        ),
        pytest.param(
            json.dumps(
                {
                    "step": {**PARENT_STEP.model_dump(mode="json"), "run_id": "nope"},
                    "depth": 0,
                    "root": ROOT.model_dump(mode="json"),
                }
            ),
            "step.run_id: Input should be a valid UUID",
            id="bad-uuid",
        ),
    ],
)
def test_decoding_names_the_first_problem_without_the_value(
    text: str,
    message: str,
) -> None:
    """Pydantic words the details; the location and kind of problem are ours to pin."""

    with pytest.raises(LineageError) as error:
        decode_step_lineage(text)

    assert str(error.value).startswith(message)
    assert "nope" not in str(error.value)


# The active step


def test_no_step_is_active_by_default() -> None:
    assert active_step_lineage() is None


def test_a_running_step_is_active_inside_its_block_only() -> None:
    lineage = parent_step(0)

    with running_step(lineage) as active:
        assert active is lineage
        assert active_step_lineage() == lineage

    assert active_step_lineage() is None


def test_a_nested_running_step_restores_the_outer_one() -> None:
    outer = parent_step(0)
    inner = parent_step(1)

    with running_step(outer):
        with running_step(inner):
            assert active_step_lineage() == inner

        assert active_step_lineage() == outer


def test_the_active_step_is_restored_after_an_error() -> None:
    with pytest.raises(RuntimeError), running_step(parent_step(0)):
        raise RuntimeError("boom")

    assert active_step_lineage() is None


def test_lineage_models_are_frozen() -> None:
    lineage = parent_step(0)

    with pytest.raises(ValidationError):
        lineage.depth = 3
