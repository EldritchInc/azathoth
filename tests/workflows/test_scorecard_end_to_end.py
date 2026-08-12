"""End-to-end tests for workflow scorecards."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
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
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


class DeterministicLanguageModel:
    """Return one deterministic response for end-to-end testing."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a successful model response."""

        assert prompt.text == "Return exactly success."

        return ModelResponse(
            text="success",
            provider="test-provider",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=1,
            total_tokens=11,
            latency_ms=100,
            estimated_cost_usd=0.02,
        )


def create_specification() -> WorkflowSpecification:
    """Create a deterministic one-step workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="scorecard-end-to-end",
            description=("Exercise workflow generation, execution, evaluation, and scoring."),
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="return-success",
                        description="Return the expected success value.",
                    ),
                    prompt=Prompt(
                        text="Return exactly success.",
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


def create_registry() -> LanguageModelRegistry:
    """Create a registry containing the deterministic test model."""

    return LanguageModelRegistry(
        {
            "test-provider/test-model": DeterministicLanguageModel(),
        }
    )


def test_workflow_scorecard_end_to_end() -> None:
    """Generate, run, evaluate, score, and serialize a workflow."""

    specification = create_specification()

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            workflow=candidate,
            context=Context(),
        )
    )

    step = run.steps[0]

    assert step.execution is not None

    evaluation = asyncio.run(
        ExactMatchEvaluator().evaluate(
            expected=ExpectedOutcome(
                description="Workflow should return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            actual=step.execution.output,
        )
    )

    scorecard = WorkflowScorer(
        policy=WorkflowScoringPolicy(
            target_latency_seconds=60.0,
            target_cost_usd=0.10,
        ),
    ).score(
        run=run,
        evaluation=evaluation,
    )

    assert run.succeeded

    assert evaluation.passed
    assert evaluation.score == pytest.approx(1.0)

    assert scorecard.quality_score == pytest.approx(1.0)
    assert scorecard.reliability_score == pytest.approx(1.0)
    assert scorecard.latency_score == pytest.approx(1.0)
    assert scorecard.cost_score == pytest.approx(1.0)
    assert scorecard.overall_score == pytest.approx(1.0)

    restored = type(scorecard).model_validate_json(scorecard.model_dump_json())

    assert restored == scorecard
