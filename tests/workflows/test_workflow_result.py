"""Tests for declared workflow results."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowResultError,
    WorkflowRun,
    WorkflowSpecification,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValue,
    WorkflowValueBinding,
    WorkflowValueReference,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.cli.test_run_show_feedback import create_run

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

OTHER_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

RUN_ID = UUID("99999999-9999-4999-8999-999999999991")


def create_step(
    step_id: UUID = STEP_ID,
    *,
    outputs: tuple[str, ...] = ("answer",),
) -> WorkflowStepSpecification:
    """Create one prompt step declaring the named outputs."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=STRATEGY_ID,
                name="Answer",
                description="Answer one request.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text="Answer the request.",
            ),
            model_selection=FixedModelSelection(
                provider="openrouter",
                model="example-model",
            ),
        ),
        outputs=tuple(WorkflowValueBinding(name=name) for name in outputs),
    )


def create_workflow(
    result: WorkflowValueReference | None,
    *,
    steps: tuple[WorkflowStepSpecification, ...] | None = None,
) -> WorkflowSpecification:
    """Create one workflow declaring the supplied result."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="answering workflow",
            description="Workflow used to test declared results.",
            version="1.0.0",
        ),
        steps=steps if steps is not None else (create_step(),),
        result=result,
    )


def create_run_with_values(
    *values: WorkflowValue,
) -> WorkflowRun:
    """Create one executed run whose single step produced the given values."""

    run = create_run(RUN_ID)

    step = run.steps[0].model_copy(
        update={
            "values": values,
        }
    )

    return run.model_copy(
        update={
            "steps": (step,),
        }
    )


def test_workflow_result_defaults_to_undeclared() -> None:
    assert create_workflow(None).result is None


def test_workflow_accepts_result_referencing_declared_output() -> None:
    reference = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="answer",
    )

    assert create_workflow(reference).result == reference


def test_workflow_result_must_reference_workflow_step() -> None:
    with pytest.raises(
        ValidationError,
        match="Workflow result must reference a producer step in the same workflow.",
    ):
        create_workflow(
            WorkflowValueReference(
                producer_step_id=OTHER_STEP_ID,
                name="answer",
            )
        )


def test_workflow_result_must_reference_declared_output() -> None:
    with pytest.raises(
        ValidationError,
        match="Workflow result must reference an output declared by the producer step.",
    ):
        create_workflow(
            WorkflowValueReference(
                producer_step_id=STEP_ID,
                name="summary",
            )
        )


def test_workflow_result_may_reference_any_step() -> None:
    reference = WorkflowValueReference(
        producer_step_id=STEP_ID,
        name="answer",
    )

    workflow = create_workflow(
        reference,
        steps=(
            create_step(),
            create_step(OTHER_STEP_ID, outputs=("audit",)),
        ),
    )

    assert workflow.result == reference


def test_workflow_document_round_trips_declared_result() -> None:
    workflow = create_workflow(
        WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="answer",
        )
    )

    document = encode_workflow_document(workflow)

    assert '"result": {' in document
    assert decode_workflow_document(document) == workflow


def test_workflow_document_without_result_decodes_as_undeclared() -> None:
    document = encode_workflow_document(create_workflow(None)).replace(
        ',\n  "result": null',
        "",
    )

    assert '"result"' not in document
    assert decode_workflow_document(document).result is None


def test_workflow_result_returns_declared_value() -> None:
    run = create_run_with_values(
        WorkflowValue(name="audit", value="ignored", producer_step_id=STEP_ID),
        WorkflowValue(name="answer", value={"label": "refund"}, producer_step_id=STEP_ID),
    )

    assert workflow_result(
        run,
        WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
    ) == {"label": "refund"}


def test_workflow_result_rejects_unproduced_value() -> None:
    run = create_run_with_values()

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow result 'answer' from step {STEP_ID} was not produced.$",
    ):
        workflow_result(
            run,
            WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
        )


def test_workflow_result_ignores_same_name_from_other_steps() -> None:
    run = create_run_with_values(
        WorkflowValue(name="answer", value="wrong", producer_step_id=OTHER_STEP_ID),
    )

    with pytest.raises(WorkflowResultError, match="was not produced"):
        workflow_result(
            run,
            WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
        )


def test_workflow_result_rejects_skipped_producer() -> None:
    run = create_run(RUN_ID)

    skipped = WorkflowStepRun(
        step_id=OTHER_STEP_ID,
        layer_index=1,
        status=WorkflowStepStatus.SKIPPED,
    )

    run = run.model_copy(
        update={
            "steps": (*run.steps, skipped),
        }
    )

    with pytest.raises(WorkflowResultError, match="was not produced"):
        workflow_result(
            run,
            WorkflowValueReference(producer_step_id=OTHER_STEP_ID, name="answer"),
        )


def test_workflow_result_rejects_duplicate_value() -> None:
    run = create_run_with_values(
        WorkflowValue(name="answer", value="first", producer_step_id=STEP_ID),
        WorkflowValue(name="answer", value="second", producer_step_id=STEP_ID),
    )

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow result 'answer' from step {STEP_ID} was produced more than once.$",
    ):
        workflow_result(
            run,
            WorkflowValueReference(producer_step_id=STEP_ID, name="answer"),
        )
