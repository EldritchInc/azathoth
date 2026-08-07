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
    WorkflowCandidateStep,
    WorkflowMetadata,
)

WORKFLOW_ID = UUID("7af83b9b-9dc2-4729-9165-7a3702f0d758")
STEP_ONE_ID = UUID("3c903a80-2f48-45d2-8f1c-d67a13b6c96b")
STEP_TWO_ID = UUID("c95c5d69-9f95-4dc5-b7e5-36bc2f2a6488")

STEP_ONE_STRATEGY_ID = UUID("44e46227-c971-4f9a-b53e-2ef80173b9dc")
STEP_TWO_STRATEGY_ID = UUID("18ad51c7-c213-49cc-8e71-ae85bbdbb262")


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
    """Create a deterministic executable workflow strategy."""

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
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=create_strategy(
                    identifier=STEP_ONE_STRATEGY_ID,
                    name="Classifier",
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_TWO_ID,
                strategy=create_strategy(
                    identifier=STEP_TWO_STRATEGY_ID,
                    name="Reasoner",
                ),
                depends_on=(STEP_ONE_ID,),
            ),
        ),
    )


def test_workflow_candidate_records_metadata_and_steps() -> None:
    workflow = create_candidate()

    assert workflow.metadata.id == WORKFLOW_ID
    assert tuple(step.strategy.metadata.name for step in workflow.steps) == (
        "Classifier",
        "Reasoner",
    )


def test_workflow_candidate_preserves_step_order() -> None:
    workflow = create_candidate()

    assert workflow.steps[0].id == STEP_ONE_ID
    assert workflow.steps[0].strategy.metadata.id == (STEP_ONE_STRATEGY_ID)
    assert workflow.steps[0].strategy.metadata.name == "Classifier"

    assert workflow.steps[1].id == STEP_TWO_ID
    assert workflow.steps[1].strategy.metadata.id == (STEP_TWO_STRATEGY_ID)
    assert workflow.steps[1].strategy.metadata.name == "Reasoner"


def test_workflow_candidate_preserves_dependency_topology() -> None:
    workflow = create_candidate()

    assert workflow.steps[0].depends_on == ()
    assert workflow.steps[1].depends_on == (STEP_ONE_ID,)


def test_workflow_candidate_derives_execution_layers() -> None:
    workflow = create_candidate()

    layers = workflow.execution_layers()

    assert tuple(tuple(step.id for step in layer) for layer in layers) == (
        (STEP_ONE_ID,),
        (STEP_TWO_ID,),
    )


def test_workflow_candidate_is_immutable() -> None:
    workflow = create_candidate()

    with pytest.raises(FrozenInstanceError):
        workflow.steps = ()  # type: ignore[misc]


def test_workflow_candidate_step_is_immutable() -> None:
    workflow = create_candidate()

    with pytest.raises(FrozenInstanceError):
        workflow.steps[0].depends_on = (STEP_TWO_ID,)  # type: ignore[misc]
