"""Tests for executable workflow candidates."""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowMetadata,
)

WORKFLOW_ID = UUID("7af83b9b-9dc2-4729-9165-7a3702f0d758")
STEP_ONE_ID = UUID("3c903a80-2f48-45d2-8f1c-d67a13b6c96b")
STEP_TWO_ID = UUID("c95c5d69-9f95-4dc5-b7e5-36bc2f2a6488")


class StubStrategy:
    """Deterministic executable workflow step."""

    def __init__(self, metadata: StrategyMetadata) -> None:
        self._metadata = metadata

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        return self._metadata

    async def run(self, _context: Context) -> StrategyOutcome:
        """Return a deterministic placeholder outcome."""

        return StrategyOutcome(output=None)


def create_strategy(
    *,
    identifier: UUID,
    name: str,
) -> Strategy:
    """Create a deterministic executable workflow step."""

    return StubStrategy(
        metadata=StrategyMetadata(
            id=identifier,
            name=name,
            description=f"{name} description.",
            version="1.0.0",
        )
    )


def create_candidate() -> WorkflowCandidate:
    """Create a deterministic executable workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Support workflow",
            description="Classify and reason about a support request.",
            version="1.0.0",
        ),
        steps=(
            create_strategy(
                identifier=STEP_ONE_ID,
                name="Classifier",
            ),
            create_strategy(
                identifier=STEP_TWO_ID,
                name="Reasoner",
            ),
        ),
    )


def test_workflow_candidate_records_metadata_and_steps() -> None:
    workflow = create_candidate()

    assert workflow.metadata.id == WORKFLOW_ID
    assert tuple(step.metadata.name for step in workflow.steps) == (
        "Classifier",
        "Reasoner",
    )


def test_workflow_candidate_preserves_step_order() -> None:
    workflow = create_candidate()

    assert workflow.steps[0].metadata.id == STEP_ONE_ID
    assert workflow.steps[0].metadata.name == "Classifier"
    assert workflow.steps[1].metadata.id == STEP_TWO_ID
    assert workflow.steps[1].metadata.name == "Reasoner"


def test_workflow_candidate_is_immutable() -> None:
    workflow = create_candidate()

    with pytest.raises(FrozenInstanceError):
        workflow.steps = ()  # type: ignore[misc]
