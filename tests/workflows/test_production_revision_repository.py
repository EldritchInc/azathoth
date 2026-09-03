"""Tests for in-memory workflow production revision persistence."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    WorkflowMetadata,
    WorkflowProductionRevision,
    WorkflowProductionRevisionRepository,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    require_workflow_production_revision_repository,
)

FIRST_REVISION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_REVISION_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

FIRST_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
SECOND_STEP_ID = UUID("66666666-6666-6666-6666-666666666666")

FIRST_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")
SECOND_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

CREATED_AT = datetime(
    2026,
    9,
    3,
    1,
    0,
    tzinfo=UTC,
)


def create_revision(
    *,
    revision_id: UUID = FIRST_REVISION_ID,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    step_id: UUID = FIRST_STEP_ID,
    strategy_id: UUID = FIRST_STRATEGY_ID,
    model: str = "production-model",
) -> WorkflowProductionRevision:
    """Create deterministic historical production revision."""

    state = WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"production-{workflow_id}",
                description="Exercise production revision persistence.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=step_id,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=strategy_id,
                            name="production-prompt",
                            description="Exercise production revision persistence.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return success.",
                        ),
                        model_selection=FixedModelSelection(
                            provider="test-provider",
                            model=model,
                        ),
                    ),
                ),
            ),
        )
    )

    return WorkflowProductionRevision(
        id=revision_id,
        state=state,
        created_at=CREATED_AT,
    )


def test_in_memory_production_revision_repository_satisfies_protocol() -> None:
    repository: WorkflowProductionRevisionRepository = (
        InMemoryWorkflowProductionRevisionRepository()
    )

    assert (
        require_workflow_production_revision_repository(
            repository,
        )
        is repository
    )


def test_in_memory_production_revision_repository_starts_empty() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    assert repository.revisions() == ()
    assert repository.get(FIRST_REVISION_ID) is None


def test_in_memory_production_revision_repository_saves_revision() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    revision = create_revision()

    repository.save(
        revision,
    )

    assert repository.get(FIRST_REVISION_ID) is revision
    assert repository.revisions() == (revision,)


def test_in_memory_production_revision_repository_preserves_insertion_order() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    first = create_revision()

    second = create_revision(
        revision_id=SECOND_REVISION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.revisions() == (
        first,
        second,
    )


def test_in_memory_production_revision_repository_rejects_duplicate_revision() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    revision = create_revision()

    repository.save(revision)

    with pytest.raises(
        ValueError,
        match=f"Workflow production revision {FIRST_REVISION_ID} already exists",
    ):
        repository.save(revision)


def test_in_memory_repository_preserves_multiple_revisions_for_workflow() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    first = create_revision(
        revision_id=FIRST_REVISION_ID,
        model="first-model",
    )

    second = create_revision(
        revision_id=SECOND_REVISION_ID,
        model="second-model",
    )

    repository.save(first)
    repository.save(second)

    assert repository.revisions_for_workflow(FIRST_WORKFLOW_ID) == (
        first,
        second,
    )


def test_in_memory_production_revision_repository_filters_by_workflow() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    first = create_revision()

    second = create_revision(
        revision_id=SECOND_REVISION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        step_id=SECOND_STEP_ID,
        strategy_id=SECOND_STRATEGY_ID,
    )

    repository.save(first)
    repository.save(second)

    assert repository.revisions_for_workflow(FIRST_WORKFLOW_ID) == (first,)

    assert repository.revisions_for_workflow(SECOND_WORKFLOW_ID) == (second,)


def test_in_memory_production_revision_repository_returns_empty_for_unknown_workflow() -> None:
    repository = InMemoryWorkflowProductionRevisionRepository()

    repository.save(
        create_revision(),
    )

    assert repository.revisions_for_workflow(SECOND_WORKFLOW_ID) == ()
