"""Tests for promoting declared workflow results to production emissions."""

import pytest

from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    WorkflowProductionEmission,
    WorkflowResultError,
    WorkflowValue,
    emit_production_result,
    promote_workflow_candidate,
)
from tests.cli.test_run_show_feedback import create_run
from tests.workflows.test_promotion import (
    PROMPT_STEP_ID,
    WORKFLOW_ID,
    create_candidate,
    create_workflow,
)


def test_promotion_emits_declared_result() -> None:
    specification = create_workflow()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    assert specification.result is not None
    assert revision.state.emissions == (
        WorkflowProductionEmission(
            name="result",
            source=specification.result,
        ),
    )


def test_promoted_state_emits_result_value_to_callers() -> None:
    specification = create_workflow()

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    run = create_run(WORKFLOW_ID)

    run = run.model_copy(
        update={
            "steps": (
                run.steps[0].model_copy(
                    update={
                        "step_id": PROMPT_STEP_ID,
                        "values": (
                            WorkflowValue(
                                name="answer",
                                value="success",
                                producer_step_id=PROMPT_STEP_ID,
                            ),
                        ),
                    }
                ),
            ),
        }
    )

    assert emit_production_result(
        state=revision.state,
        run=run,
    ) == {
        "result": "success",
    }


def test_promotion_rejects_workflow_without_result_and_persists_nothing() -> None:
    specification = create_workflow().model_copy(
        update={
            "result": None,
        }
    )

    state_repository = InMemoryWorkflowProductionStateRepository()
    revision_repository = InMemoryWorkflowProductionRevisionRepository()

    with pytest.raises(
        WorkflowResultError,
        match=f"^Workflow {WORKFLOW_ID} does not declare a result.$",
    ):
        promote_workflow_candidate(
            specification=specification,
            candidate=create_candidate(specification),
            repository=state_repository,
            revision_repository=revision_repository,
        )

    assert state_repository.get(WORKFLOW_ID) is None
    assert revision_repository.revisions() == ()
