"""Tests for executable workflow candidates."""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.context import Context
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowCandidateStep,
    WorkflowMetadata,
)

WORKFLOW_ID = UUID("7af83b9b-9dc2-4729-9165-7a3702f0d758")
SECOND_WORKFLOW_ID = UUID("88888888-8888-8888-8888-888888888888")

STEP_ONE_ID = UUID("3c903a80-2f48-45d2-8f1c-d67a13b6c96b")
STEP_TWO_ID = UUID("c95c5d69-9f95-4dc5-b7e5-36bc2f2a6488")

STEP_ONE_STRATEGY_ID = UUID("44e46227-c971-4f9a-b53e-2ef80173b9dc")
STEP_TWO_STRATEGY_ID = UUID("18ad51c7-c213-49cc-8e71-ae85bbdbb262")
ALTERNATE_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")


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


def create_candidate(
    *,
    workflow_id: UUID = WORKFLOW_ID,
    first_strategy_id: UUID = STEP_ONE_STRATEGY_ID,
    second_strategy_id: UUID = STEP_TWO_STRATEGY_ID,
) -> WorkflowCandidate:
    """Create a deterministic executable workflow candidate."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name="Support workflow",
            description="Classify and reason about a support request.",
            version="1.0.0",
        ),
        steps=(
            WorkflowCandidateStep(
                id=STEP_ONE_ID,
                strategy=create_strategy(
                    identifier=first_strategy_id,
                    name="Classifier",
                ),
            ),
            WorkflowCandidateStep(
                id=STEP_TWO_ID,
                strategy=create_strategy(
                    identifier=second_strategy_id,
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
    assert workflow.steps[0].strategy.metadata.id == STEP_ONE_STRATEGY_ID
    assert workflow.steps[0].strategy.metadata.name == "Classifier"

    assert workflow.steps[1].id == STEP_TWO_ID
    assert workflow.steps[1].strategy.metadata.id == STEP_TWO_STRATEGY_ID
    assert workflow.steps[1].strategy.metadata.name == "Reasoner"


def test_workflow_candidate_preserves_dependency_topology() -> None:
    workflow = create_candidate()

    assert workflow.steps[0].depends_on == ()
    assert workflow.steps[1].depends_on == (STEP_ONE_ID,)


def test_workflow_candidate_derives_signature() -> None:
    workflow = create_candidate()

    assert workflow.signature == WorkflowCandidateSignature(
        workflow_id=WORKFLOW_ID,
        strategy_ids=(
            STEP_ONE_STRATEGY_ID,
            STEP_TWO_STRATEGY_ID,
        ),
    )


def test_workflow_candidate_signature_is_deterministic() -> None:
    first = create_candidate()
    second = create_candidate()

    assert first.signature == second.signature
    assert hash(first.signature) == hash(second.signature)


def test_workflow_candidate_signature_distinguishes_resolved_strategies() -> None:
    baseline = create_candidate()
    alternative = create_candidate(
        second_strategy_id=ALTERNATE_STRATEGY_ID,
    )

    assert baseline.signature != alternative.signature


def test_workflow_candidate_signature_distinguishes_workflows() -> None:
    first = create_candidate()
    second = create_candidate(
        workflow_id=SECOND_WORKFLOW_ID,
    )

    assert first.signature != second.signature


def test_workflow_candidate_signature_preserves_strategy_order() -> None:
    workflow = create_candidate()

    assert workflow.signature.strategy_ids == (
        STEP_ONE_STRATEGY_ID,
        STEP_TWO_STRATEGY_ID,
    )


def test_workflow_candidate_signature_is_immutable() -> None:
    signature = create_candidate().signature

    with pytest.raises(ValidationError):
        signature.workflow_id = SECOND_WORKFLOW_ID


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
