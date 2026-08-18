"""Tests for SQLite workflow specification persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import ModelRequirements, Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    ToolStepSpecification,
    WorkflowCondition,
    WorkflowConditionOperator,
    WorkflowFailurePolicy,
    WorkflowInputBinding,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
PROMPT_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
TOOL_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
ROUTED_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
PROMPT_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")
ROUTED_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")


def create_prompt_specification(
    *,
    strategy_id: UUID,
    name: str,
) -> PromptStrategySpec:
    """Create a deterministic prompt-backed specification."""

    return PromptStrategySpec(
        metadata=StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        ),
        prompt=Prompt(
            text=f"Execute {name}.",
        ),
        model_requirements=ModelRequirements(),
    )


def create_workflow(
    *,
    workflow_id: UUID = WORKFLOW_ID,
    name: str = "Persisted workflow",
) -> WorkflowSpecification:
    """Create a workflow exercising durable specification fields."""

    word_count_reference = WorkflowValueReference(
        producer_step_id=TOOL_STEP_ID,
        name="word_count",
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description="Exercise SQLite workflow persistence.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=PROMPT_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=PROMPT_STRATEGY_ID,
                    name="produce text",
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="text",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=TOOL_STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime="python",
                    ),
                ),
                depends_on=(PROMPT_STEP_ID,),
                inputs=(
                    WorkflowInputBinding(
                        name="text",
                        source=WorkflowValueReference(
                            producer_step_id=PROMPT_STEP_ID,
                            name="text",
                        ),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="word_count",
                        path=("word_count",),
                    ),
                ),
                retry_policy=WorkflowRetryPolicy(
                    max_attempts=3,
                    initial_delay_seconds=0.1,
                    backoff_multiplier=2.0,
                    maximum_delay_seconds=1.0,
                ),
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            WorkflowStepSpecification(
                id=ROUTED_STEP_ID,
                specification=create_prompt_specification(
                    strategy_id=ROUTED_STRATEGY_ID,
                    name="route result",
                ),
                depends_on=(TOOL_STEP_ID,),
                conditions=(
                    WorkflowCondition(
                        source=word_count_reference,
                        operator=(WorkflowConditionOperator.GREATER_THAN_OR_EQUAL),
                        expected=4,
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="route",
                    ),
                ),
            ),
        ),
    )


def test_sqlite_repository_saves_and_gets_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflows.db")
    specification = create_workflow()

    repository.save(specification)

    assert repository.get(WORKFLOW_ID) == specification


def test_sqlite_repository_returns_none_for_unknown_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflows.db")

    assert repository.get(WORKFLOW_ID) is None


def test_sqlite_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflows.db")

    first = create_workflow()
    second = create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        name="Second workflow",
    )

    repository.save(first)
    repository.save(second)

    assert repository.specifications() == (
        first,
        second,
    )


def test_sqlite_repository_rejects_duplicate_workflow(
    tmp_path: Path,
) -> None:
    repository = SQLiteWorkflowRepository(tmp_path / "workflows.db")
    specification = create_workflow()

    repository.save(specification)

    with pytest.raises(
        ValueError,
        match=f"Workflow specification {WORKFLOW_ID} already exists",
    ):
        repository.save(specification)


def test_sqlite_repository_reconstructs_complete_workflow(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflows.db"

    first_repository = SQLiteWorkflowRepository(database)
    specification = create_workflow()

    first_repository.save(specification)

    reconstructed_repository = SQLiteWorkflowRepository(database)
    restored = reconstructed_repository.get(WORKFLOW_ID)

    assert restored == specification
    assert restored is not specification

    assert restored is not None
    assert len(restored.steps) == 3

    prompt_step = restored.steps[0]
    tool_step = restored.steps[1]
    routed_step = restored.steps[2]

    assert isinstance(
        prompt_step.specification,
        PromptStrategySpec,
    )

    assert isinstance(
        tool_step.specification,
        ToolStepSpecification,
    )

    assert tool_step.specification.requirement == ToolRequirement(
        name="word_count",
        version="1.0.0",
        runtime="python",
    )

    assert tool_step.depends_on == (PROMPT_STEP_ID,)

    assert tool_step.inputs == (
        WorkflowInputBinding(
            name="text",
            source=WorkflowValueReference(
                producer_step_id=PROMPT_STEP_ID,
                name="text",
            ),
        ),
    )

    assert tool_step.outputs == (
        WorkflowValueBinding(
            name="word_count",
            path=("word_count",),
        ),
    )

    assert tool_step.retry_policy == WorkflowRetryPolicy(
        max_attempts=3,
        initial_delay_seconds=0.1,
        backoff_multiplier=2.0,
        maximum_delay_seconds=1.0,
    )

    assert tool_step.failure_policy is WorkflowFailurePolicy.SKIP_DEPENDENTS

    assert routed_step.conditions == (
        WorkflowCondition(
            source=WorkflowValueReference(
                producer_step_id=TOOL_STEP_ID,
                name="word_count",
            ),
            operator=(WorkflowConditionOperator.GREATER_THAN_OR_EQUAL),
            expected=4,
        ),
    )


def test_sqlite_repository_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflows.db"
    specification = create_workflow()

    SQLiteWorkflowRepository(database).save(specification)

    restored = SQLiteWorkflowRepository(database).specifications()

    assert restored == (specification,)
