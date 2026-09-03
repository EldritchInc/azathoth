"""Tests for immutable workflow production revisions."""

from datetime import UTC, datetime
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
    WorkflowProductionRevision,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

REVISION_ID = UUID("11111111-1111-1111-1111-111111111111")
WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

CREATED_AT = datetime(
    2026,
    9,
    3,
    1,
    0,
    tzinfo=UTC,
)


def create_production_state() -> WorkflowProductionState:
    """Create deterministic workflow production state."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="revision-workflow",
                description="Exercise immutable production revision identity.",
                version="1.0.0",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=STEP_ID,
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=STRATEGY_ID,
                            name="revision-prompt",
                            description="Exercise production revision identity.",
                            version="1.0.0",
                        ),
                        prompt=Prompt(
                            text="Return success.",
                        ),
                        model_selection=FixedModelSelection(
                            provider="test-provider",
                            model="production-model",
                        ),
                    ),
                ),
            ),
        )
    )


def test_production_revision_records_exact_production_state() -> None:
    state = create_production_state()

    revision = WorkflowProductionRevision(
        id=REVISION_ID,
        state=state,
        created_at=CREATED_AT,
    )

    assert revision.state is state


def test_production_revision_has_independent_identity() -> None:
    state = create_production_state()

    first = WorkflowProductionRevision(
        state=state,
    )

    second = WorkflowProductionRevision(
        state=state,
    )

    assert first.id != second.id
    assert first.state == second.state


def test_production_revision_derives_workflow_identity() -> None:
    revision = WorkflowProductionRevision(
        id=REVISION_ID,
        state=create_production_state(),
        created_at=CREATED_AT,
    )

    assert revision.workflow_id == WORKFLOW_ID


def test_production_revision_preserves_creation_time() -> None:
    revision = WorkflowProductionRevision(
        id=REVISION_ID,
        state=create_production_state(),
        created_at=CREATED_AT,
    )

    assert revision.created_at == CREATED_AT


def test_production_revision_is_immutable() -> None:
    revision = WorkflowProductionRevision(
        id=REVISION_ID,
        state=create_production_state(),
        created_at=CREATED_AT,
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        revision.__setattr__(
            "id",
            UUID("55555555-5555-5555-5555-555555555555"),
        )
