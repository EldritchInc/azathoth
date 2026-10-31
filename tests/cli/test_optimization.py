"""Tests for configured workflow optimization application services."""

import asyncio
from uuid import UUID

import pytest

from azathoth.cli import optimize_configured_workflow
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelPricing,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

EXPENSIVE_IDENTIFIER = "test-provider/expensive"
CHEAP_IDENTIFIER = "test-provider/cheap"


class CostedDeterministicLanguageModel:
    """Return deterministic output with configured execution cost."""

    def __init__(
        self,
        *,
        model: str,
        estimated_cost_usd: float,
    ) -> None:
        self._model = model
        self._estimated_cost_usd = estimated_cost_usd

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return one deterministic successful model response."""

        prompt_tokens = len(prompt.text.split())
        completion_tokens = 1

        return ModelResponse(
            text="success",
            provider="test-provider",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=(prompt_tokens + completion_tokens),
            latency_ms=0,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow allowing portfolio model selection."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="optimization-test",
            description="Exercise configured workflow optimization.",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="prompt",
                        description="Return deterministic output.",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="answer",
                    ),
                ),
            ),
        ),
        result=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="answer",
        ),
    )


def create_models() -> ModelCatalog:
    """Create deterministic expensive and cheap provider models."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="test-provider",
                model="expensive",
                display_name="Expensive",
                context_window_tokens=4096,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=10.0,
                    output_usd_per_million_tokens=20.0,
                ),
            ),
            ModelMetadata(
                provider="test-provider",
                model="cheap",
                display_name="Cheap",
                context_window_tokens=4096,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=1.0,
                    output_usd_per_million_tokens=2.0,
                ),
            ),
        ),
    )


def create_portfolio() -> ModelPortfolio:
    """Authorize both deterministic provider models."""

    return ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider="test-provider",
                model="expensive",
            ),
            ModelPortfolioEntry(
                provider="test-provider",
                model="cheap",
            ),
        ),
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable implementations for both models."""

    return LanguageModelRegistry(
        models={
            EXPENSIVE_IDENTIFIER: CostedDeterministicLanguageModel(
                model="expensive",
                estimated_cost_usd=0.10,
            ),
            CHEAP_IDENTIFIER: CostedDeterministicLanguageModel(
                model="cheap",
                estimated_cost_usd=0.01,
            ),
        }
    )


def create_runtime() -> AzathothRuntime:
    """Create a runtime capable of empirical model substitution."""

    workflow = create_workflow()

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(workflow,),
        ),
        models=create_models(),
        portfolio=create_portfolio(),
        language_models=create_registry(),
    )


BENCHMARK_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def case_id(
    index: int,
) -> UUID:
    """Return the deterministic identifier of one benchmark case."""

    return UUID(int=BENCHMARK_ID.int + index)


def create_benchmark(
    *expectations: ExpectedOutcome,
) -> BenchmarkDataset:
    """Create a benchmark with one case per expectation, in order."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="optimization",
        description="Benchmark used for optimization tests.",
        cases=tuple(
            BenchmarkCase(
                id=case_id(index),
                input=f"request {index}",
                expected=expected,
            )
            for index, expected in enumerate(
                expectations,
                start=1,
            )
        ),
    )


def test_optimize_configured_workflow_runs_requested_generations() -> None:
    runtime = create_runtime()

    session = asyncio.run(
        optimize_configured_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=2,
        )
    )

    assert len(session.generations) == 2


def test_optimize_configured_workflow_starts_from_runtime_candidate() -> None:
    runtime = create_runtime()

    session = asyncio.run(
        optimize_configured_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=1,
        )
    )

    assert len(session.initial_candidates) == 1
    assert session.initial_candidates[0].metadata.id == WORKFLOW_ID


def test_optimize_configured_workflow_generates_cheaper_candidate() -> None:
    runtime = create_runtime()

    session = asyncio.run(
        optimize_configured_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=1,
        )
    )

    generation = session.generations[0]

    assert len(generation.candidates) == 2


def test_optimize_configured_workflow_empirically_evaluates_generated_candidate() -> None:
    runtime = create_runtime()

    session = asyncio.run(
        optimize_configured_workflow(
            runtime=runtime,
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=2,
        )
    )

    first_experiment = session.generations[0].previous_experiment
    second_experiment = session.generations[1].previous_experiment

    assert len(first_experiment.evidence) == 1
    assert len(second_experiment.evidence) == 2

    assert second_experiment.winner.overall_score >= first_experiment.winner.overall_score


def test_optimize_configured_workflow_averages_quality_across_cases() -> None:
    session = asyncio.run(
        optimize_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
                ExpectedOutcome(
                    description="Workflow returns failure.",
                    value="failure",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=1,
        )
    )

    evidence = session.generations[0].previous_experiment.evidence

    assert len(evidence) == 1
    assert evidence[0].scorecard.quality_score == 0.5


def test_optimize_configured_workflow_rejects_empty_benchmark_before_generating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = create_runtime()

    def fail_generation(*args: object, **kwargs: object) -> object:
        raise AssertionError("Candidates must not be generated.")

    monkeypatch.setattr(
        runtime,
        "generate_workflow_candidate",
        fail_generation,
    )

    with pytest.raises(
        ValueError,
        match=f"^Benchmark {BENCHMARK_ID} has no cases.$",
    ):
        asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
                dataset=create_benchmark(),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.01,
                ),
                max_generations=1,
            )
        )


def model_identifier(
    candidate: WorkflowCandidate,
) -> str:
    """Return the model bound to the candidate's prompt step."""

    strategy = candidate.steps[0].strategy

    assert isinstance(strategy, PromptStrategy)
    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def test_optimize_configured_workflow_compares_models_in_one_generation() -> None:
    session = asyncio.run(
        optimize_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            dataset=create_benchmark(
                ExpectedOutcome(
                    description="Workflow returns success.",
                    value="success",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            scoring_policy=WorkflowScoringPolicy(
                target_latency_seconds=60.0,
                target_cost_usd=0.01,
            ),
            max_generations=1,
        )
    )

    assert session.final_experiment is not None
    assert len(session.final_experiment.evidence) == 2
    assert session.winner is not None
    assert model_identifier(session.winner) == CHEAP_IDENTIFIER
