"""End-to-end tests for workflow optimization sessions."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.optimization import (
    ReplayWorkflowOptimizer,
    WorkflowOptimizationSessionRunner,
)
from azathoth.prompting import PromptStrategySpec
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
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

BEST_WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
WEAKEST_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")
BEST_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
WEAKEST_STEP_ID = UUID("44444444-4444-4444-4444-444444444444")
BEST_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")
WEAKEST_STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

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
            description="Workflow used for end-to-end session tests.",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=f"{name}-strategy",
                        description="Return a deterministic session result.",
                    ),
                    prompt=Prompt(
                        text="Produce the configured deterministic result.",
                    ),
                    model_requirements=ModelRequirements(),
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
    """Create a registry containing one configured test model."""

    return LanguageModelRegistry(
        {
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                text=text,
                estimated_cost_usd=estimated_cost_usd,
            ),
        }
    )


def test_workflow_optimization_session_end_to_end() -> None:
    """Run multiple workflow optimization generations end to end."""

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

    candidates = (
        weakest_candidate,
        best_candidate,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=WorkflowExperimentRunner(
                scorer=WorkflowScorer(
                    policy=WorkflowScoringPolicy(
                        target_latency_seconds=60.0,
                        target_cost_usd=0.10,
                    ),
                ),
            ),
            optimizer=ReplayWorkflowOptimizer(),
        ).run(
            initial_candidates=candidates,
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Workflow should return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    assert session.initial_candidates == candidates
    assert session.initial_candidates[0] is weakest_candidate
    assert session.initial_candidates[1] is best_candidate

    assert tuple(generation.generation for generation in session.generations) == (
        1,
        2,
    )

    first_generation = session.generations[0]
    second_generation = session.generations[1]

    assert first_generation.previous_experiment.scorecards[0].quality_score == pytest.approx(0.0)
    assert first_generation.previous_experiment.scorecards[0].cost_score == pytest.approx(0.25)
    assert first_generation.previous_experiment.scorecards[1].quality_score == pytest.approx(1.0)
    assert first_generation.previous_experiment.scorecards[1].cost_score == pytest.approx(1.0)

    assert first_generation.previous_experiment.winner.overall_score == pytest.approx(1.0)
    assert second_generation.previous_experiment.winner.overall_score == pytest.approx(1.0)

    assert first_generation.candidates == candidates
    assert second_generation.candidates == candidates

    assert first_generation.candidates[0] is weakest_candidate
    assert first_generation.candidates[1] is best_candidate
    assert second_generation.candidates[0] is weakest_candidate
    assert second_generation.candidates[1] is best_candidate

    assert tuple(candidate.metadata.id for candidate in first_generation.candidates) == (
        WEAKEST_WORKFLOW_ID,
        BEST_WORKFLOW_ID,
    )
    assert tuple(candidate.metadata.id for candidate in second_generation.candidates) == (
        WEAKEST_WORKFLOW_ID,
        BEST_WORKFLOW_ID,
    )

    assert first_generation.previous_experiment == second_generation.previous_experiment
