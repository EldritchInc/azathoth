"""End-to-end tests for workflow experiments."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowExperimentResult,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

BEST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

BALANCED_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

WEAKEST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")

BEST_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

BALANCED_STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

WEAKEST_STEP_ID = UUID("66666666-6666-6666-6666-666666666666")

BEST_STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

BALANCED_STRATEGY_ID = UUID("88888888-8888-8888-8888-888888888888")

WEAKEST_STRATEGY_ID = UUID("99999999-9999-9999-9999-999999999999")

MODEL_IDENTIFIER = "test-provider/test-model"


class DeterministicLanguageModel:
    """Return one configured deterministic model response."""

    def __init__(
        self,
        *,
        text: str,
        estimated_cost_usd: float,
    ) -> None:
        self._text = text
        self._estimated_cost_usd = estimated_cost_usd

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return the configured deterministic response."""

        assert prompt.text == "Produce the configured deterministic result."

        return ModelResponse(
            text=self._text,
            provider="test-provider",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=1,
            total_tokens=11,
            latency_ms=100,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def create_specification(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
) -> WorkflowSpecification:
    """Create a deterministic workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=("Workflow used for end-to-end experiment tests."),
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{name}-strategy",
                        description=("Return a deterministic test result."),
                    ),
                    prompt=Prompt(
                        text=("Produce the configured deterministic result."),
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create a catalog containing the deterministic test model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="test-model",
                display_name="Test Model",
                context_window_tokens=4096,
            ),
        ),
    )


def create_registry(
    *,
    text: str,
    estimated_cost_usd: float,
) -> LanguageModelRegistry:
    """Create a registry containing one configured model."""

    return LanguageModelRegistry(
        {
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                text=text,
                estimated_cost_usd=estimated_cost_usd,
            ),
        }
    )


def test_workflow_experiment_end_to_end() -> None:
    """Generate, execute, evaluate, score, rank, and serialize workflows."""

    catalog = create_catalog()

    best_candidate = generate_workflow_candidate(
        specification=create_specification(
            workflow_id=BEST_WORKFLOW_ID,
            step_id=BEST_STEP_ID,
            strategy_id=BEST_STRATEGY_ID,
            name="best-workflow",
        ),
        catalog=catalog,
        registry=create_registry(
            text="success",
            estimated_cost_usd=0.05,
        ),
    )

    balanced_candidate = generate_workflow_candidate(
        specification=create_specification(
            workflow_id=BALANCED_WORKFLOW_ID,
            step_id=BALANCED_STEP_ID,
            strategy_id=BALANCED_STRATEGY_ID,
            name="balanced-workflow",
        ),
        catalog=catalog,
        registry=create_registry(
            text="failure",
            estimated_cost_usd=0.05,
        ),
    )

    weakest_candidate = generate_workflow_candidate(
        specification=create_specification(
            workflow_id=WEAKEST_WORKFLOW_ID,
            step_id=WEAKEST_STEP_ID,
            strategy_id=WEAKEST_STRATEGY_ID,
            name="weakest-workflow",
        ),
        catalog=catalog,
        registry=create_registry(
            text="failure",
            estimated_cost_usd=0.40,
        ),
    )

    result = asyncio.run(
        WorkflowExperimentRunner(
            scorer=WorkflowScorer(
                policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.10,
                ),
            ),
        ).run(
            workflows=(
                weakest_candidate,
                balanced_candidate,
                best_candidate,
            ),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Workflow should return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
        )
    )

    assert len(result.scorecards) == 3

    weakest_scorecard = result.scorecards[0]
    balanced_scorecard = result.scorecards[1]
    best_scorecard = result.scorecards[2]

    assert best_scorecard.quality_score == pytest.approx(1.0)
    assert best_scorecard.reliability_score == pytest.approx(1.0)
    assert best_scorecard.latency_score == pytest.approx(1.0)
    assert best_scorecard.cost_score == pytest.approx(1.0)
    assert best_scorecard.overall_score == pytest.approx(1.0)

    assert balanced_scorecard.quality_score == pytest.approx(0.0)
    assert balanced_scorecard.reliability_score == pytest.approx(1.0)
    assert balanced_scorecard.latency_score == pytest.approx(1.0)
    assert balanced_scorecard.cost_score == pytest.approx(1.0)
    assert balanced_scorecard.overall_score == pytest.approx(0.75)

    assert weakest_scorecard.quality_score == pytest.approx(0.0)
    assert weakest_scorecard.reliability_score == pytest.approx(1.0)
    assert weakest_scorecard.latency_score == pytest.approx(1.0)
    assert weakest_scorecard.cost_score == pytest.approx(0.25)
    assert weakest_scorecard.overall_score == pytest.approx(0.5625)

    assert tuple(entry.scorecard for entry in result.ranking.entries) == (
        best_scorecard,
        balanced_scorecard,
        weakest_scorecard,
    )

    assert tuple(entry.rank for entry in result.ranking.entries) == (
        1,
        2,
        3,
    )

    assert result.winner == best_scorecard

    restored = WorkflowExperimentResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.winner == best_scorecard
