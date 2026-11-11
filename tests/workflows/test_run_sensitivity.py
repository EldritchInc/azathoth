"""Tests that a run records its input's label, and every step sees it (ADR 0123)."""

import asyncio
from uuid import UUID

from azathoth.context import (
    INPUT_SENSITIVITY_EVENT_TYPE,
    Context,
    StepLineage,
    child_lineage,
    context_sensitivity,
    create_lineage_event,
)
from azathoth.inputs import InputProvenance, ResolvedInput
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    WorkflowRunner,
    create_production_invocation,
    create_workflow_input_events,
)
from tests.workflows.test_run_lineage import (
    FIRST_STEP_ID,
    PARENT,
    WORKFLOW_ID,
    RecordingStrategy,
    candidate,
    step,
)

PROVENANCE = InputProvenance(
    uri="s3://claims/412.pdf",
    media_type="application/pdf",
    size_bytes=3,
    digest="a" * 64,
)


def event_types(
    context: Context,
) -> list[str]:
    return [event.event_type for event in context.events]


# Input events


def test_a_labelled_input_records_its_label_last() -> None:
    events = create_workflow_input_events(
        ResolvedInput(
            value={"claim": 412},
            media_type="application/json",
            sensitivity=Sensitivity.RESTRICTED,
        ),
        producer="test",
    )

    assert [event.event_type for event in events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
        INPUT_SENSITIVITY_EVENT_TYPE,
    ]
    assert events[-1].payload == {"sensitivity": "restricted"}
    assert events[-1].producer == "test"
    assert events[-1].occurred_at == events[0].occurred_at


def test_a_labelled_input_with_provenance_records_both() -> None:
    events = create_workflow_input_events(
        ResolvedInput(
            value=None,
            media_type="application/pdf",
            provenance=PROVENANCE,
            sensitivity=Sensitivity.PUBLIC,
        ),
        producer="test",
    )

    assert [event.event_type for event in events] == [
        WORKFLOW_INPUT_EVENT_TYPE,
        WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
        INPUT_SENSITIVITY_EVENT_TYPE,
    ]


def test_an_unlabelled_input_records_no_label() -> None:
    events = create_workflow_input_events(
        ResolvedInput(value=1, media_type="application/json"),
        producer="test",
    )

    assert [event.event_type for event in events] == [WORKFLOW_INPUT_EVENT_TYPE]


def test_an_explicitly_internal_input_records_its_label() -> None:
    events = create_workflow_input_events(
        ResolvedInput(value=1, media_type="application/json", sensitivity=Sensitivity.INTERNAL),
        producer="test",
    )

    assert events[-1].payload == {"sensitivity": "internal"}


# Production invocations


def test_a_labelled_invocation_records_its_label() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"claim": 412},
        sensitivity=Sensitivity.RESTRICTED,
    )

    assert context_sensitivity(invocation.initial_context) is Sensitivity.RESTRICTED
    assert INPUT_SENSITIVITY_EVENT_TYPE in event_types(invocation.initial_context)


def test_an_unlabelled_invocation_records_no_label() -> None:
    invocation = create_production_invocation(workflow_id=WORKFLOW_ID, payload={"claim": 412})

    assert INPUT_SENSITIVITY_EVENT_TYPE not in event_types(invocation.initial_context)
    assert context_sensitivity(invocation.initial_context) is Sensitivity.INTERNAL


def test_a_childs_invocation_carries_its_parents_label() -> None:
    labelled_parent = PARENT.model_copy(update={"sensitivity": Sensitivity.RESTRICTED})

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={"claim": 412},
        lineage=child_lineage(labelled_parent, workflow_id=WORKFLOW_ID),
    )

    assert context_sensitivity(invocation.initial_context) is Sensitivity.RESTRICTED


# What a running step sees


def seen_while_running(
    context: Context,
) -> StepLineage:
    """Return the lineage the one step of a run saw while it ran."""

    strategy = RecordingStrategy()

    asyncio.run(
        WorkflowRunner().run(workflow=candidate(step(FIRST_STEP_ID, strategy)), context=context)
    )

    (seen,) = strategy.seen

    assert seen is not None

    return seen


def labelled_context(
    label: Sensitivity,
) -> Context:
    return Context(
        events=create_workflow_input_events(
            ResolvedInput(value=1, media_type="application/json", sensitivity=label),
            producer="test",
        )
    )


def test_a_restricted_runs_steps_see_its_label() -> None:
    assert seen_while_running(labelled_context(Sensitivity.RESTRICTED)).sensitivity is (
        Sensitivity.RESTRICTED
    )


def test_an_internal_runs_steps_see_no_label() -> None:
    assert seen_while_running(Context()).sensitivity is None
    assert seen_while_running(labelled_context(Sensitivity.INTERNAL)).sensitivity is None


def test_a_child_of_a_restricted_run_sees_its_parents_label() -> None:
    labelled_parent = PARENT.model_copy(update={"sensitivity": Sensitivity.RESTRICTED})

    context = Context(
        events=(create_lineage_event(child_lineage(labelled_parent, workflow_id=WORKFLOW_ID)),)
    )

    seen = seen_while_running(context)

    assert seen.sensitivity is Sensitivity.RESTRICTED
    assert seen.depth == 3


def test_the_label_reaches_what_a_step_starts_as_a_child() -> None:
    seen = seen_while_running(labelled_context(Sensitivity.RESTRICTED))

    assert child_lineage(seen, workflow_id=UUID(int=1)).sensitivity is Sensitivity.RESTRICTED
