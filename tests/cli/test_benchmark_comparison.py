"""Tests for comparing configured workflows against one benchmark."""

import asyncio
from uuid import UUID

import pytest

from azathoth.cli import compare_configured_benchmarks
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
    PromptBinding,
    PromptTemplate,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelResponse,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import portfolio_for_catalog

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

SECOND_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

CORRECT_WORKFLOW_ID = UUID("44444444-4444-4444-8444-444444444444")

INCORRECT_WORKFLOW_ID = UUID("55555555-5555-4555-8555-555555555555")

CORRECT_STEP_ID = UUID("66666666-6666-4666-8666-666666666666")

INCORRECT_STEP_ID = UUID("77777777-7777-4777-8777-777777777777")

CORRECT_STRATEGY_ID = UUID("88888888-8888-4888-8888-888888888888")

INCORRECT_STRATEGY_ID = UUID("99999999-9999-4999-8999-999999999999")

CORRECT_MODEL_IDENTIFIER = "deterministic/correct-classifier"
INCORRECT_MODEL_IDENTIFIER = "deterministic/incorrect-classifier"


class ScoredDeterministicLanguageModel:
    """Return deterministic model output with complete scoring evidence."""

    def __init__(
        self,
        *,
        model: str,
        response_text: str,
        estimated_cost_usd: float,
    ) -> None:
        self._model = model
        self._response_text = response_text
        self._estimated_cost_usd = estimated_cost_usd

    async def complete(
        self,
        _prompt: Prompt,
    ) -> ModelResponse:
        """Return one deterministic model response."""

        return ModelResponse(
            text=self._response_text,
            provider="deterministic",
            model=self._model,
            prompt_tokens=10,
            completion_tokens=1,
            total_tokens=11,
            latency_ms=100,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic classification benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="classification",
        description="Compare configured classification workflows.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input="first",
                expected=ExpectedOutcome(
                    description="Expected positive classification.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
            BenchmarkCase(
                id=SECOND_CASE_ID,
                input="second",
                expected=ExpectedOutcome(
                    description="Expected positive classification.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def create_workflow(
    *,
    workflow_id: UUID,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    model: str,
) -> WorkflowSpecification:
    """Create one configured context-aware model workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=step_id,
                specification=ContextPromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=strategy_id,
                        name=name,
                        description=f"Classify input with {name}.",
                        version="1.0.0",
                    ),
                    template=PromptTemplate(
                        text="Classify this input: {input}",
                        bindings=(
                            PromptBinding(
                                variable_name="input",
                                event_type=WORKFLOW_INPUT_EVENT_TYPE,
                                field_name="input",
                            ),
                        ),
                    ),
                    model_selection=FixedModelSelection(
                        provider="deterministic",
                        model=model,
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_runtime() -> AzathothRuntime:
    """Create two differently performing configured workflows."""

    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="deterministic",
                model="correct-classifier",
                display_name="Correct Classifier",
                context_window_tokens=8_192,
            ),
            ModelMetadata(
                provider="deterministic",
                model="incorrect-classifier",
                display_name="Incorrect Classifier",
                context_window_tokens=8_192,
            ),
        ),
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=(
                create_workflow(
                    workflow_id=CORRECT_WORKFLOW_ID,
                    step_id=CORRECT_STEP_ID,
                    strategy_id=CORRECT_STRATEGY_ID,
                    name="correct-classifier",
                    model="correct-classifier",
                ),
                create_workflow(
                    workflow_id=INCORRECT_WORKFLOW_ID,
                    step_id=INCORRECT_STEP_ID,
                    strategy_id=INCORRECT_STRATEGY_ID,
                    name="incorrect-classifier",
                    model="incorrect-classifier",
                ),
            ),
        ),
        models=models,
        portfolio=portfolio_for_catalog(
            models,
        ),
        language_models=LanguageModelRegistry(
            models={
                CORRECT_MODEL_IDENTIFIER: ScoredDeterministicLanguageModel(
                    model="correct-classifier",
                    response_text="positive",
                    estimated_cost_usd=0.0001,
                ),
                INCORRECT_MODEL_IDENTIFIER: ScoredDeterministicLanguageModel(
                    model="incorrect-classifier",
                    response_text="negative",
                    estimated_cost_usd=0.0001,
                ),
            },
        ),
    )


def create_policy() -> WorkflowScoringPolicy:
    """Create deterministic benchmark scoring policy."""

    return WorkflowScoringPolicy(
        target_latency_seconds=5.0,
        target_cost_usd=0.001,
    )


def test_configured_comparison_ranks_workflows() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="classification",
            scoring_policy=create_policy(),
        )
    )

    assert len(ranking.entries) == 2

    assert ranking.winner.name == str(CORRECT_WORKFLOW_ID)

    assert ranking.entries[0].rank == 1

    assert ranking.entries[1].name == str(INCORRECT_WORKFLOW_ID)

    assert ranking.entries[1].rank == 2


def test_configured_comparison_preserves_score_dimensions() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="classification",
            scoring_policy=create_policy(),
        )
    )

    winner = ranking.winner.scorecard

    assert winner.quality_score == 1.0
    assert winner.reliability_score == 1.0
    assert winner.latency_score == 1.0
    assert winner.cost_score == 1.0
    assert winner.overall_score == 1.0

    loser = ranking.entries[1].scorecard

    assert loser.quality_score == 0.0
    assert loser.reliability_score == 1.0
    assert loser.latency_score == 1.0
    assert loser.cost_score == 1.0
    assert loser.overall_score == 0.75


def test_configured_comparison_uses_workflow_identifiers_as_names() -> None:
    ranking = asyncio.run(
        compare_configured_benchmarks(
            runtime=create_runtime(),
            workflow_ids=(
                CORRECT_WORKFLOW_ID,
                INCORRECT_WORKFLOW_ID,
            ),
            dataset=create_dataset(),
            output_name="classification",
            scoring_policy=create_policy(),
        )
    )

    assert {entry.name for entry in ranking.entries} == {
        str(CORRECT_WORKFLOW_ID),
        str(INCORRECT_WORKFLOW_ID),
    }


def test_configured_comparison_rejects_fewer_than_two_workflows() -> None:
    with pytest.raises(
        ValueError,
        match="At least two configured workflows",
    ):
        asyncio.run(
            compare_configured_benchmarks(
                runtime=create_runtime(),
                workflow_ids=(CORRECT_WORKFLOW_ID,),
                dataset=create_dataset(),
                output_name="classification",
                scoring_policy=create_policy(),
            )
        )


def test_configured_comparison_rejects_duplicate_workflows() -> None:
    with pytest.raises(
        ValueError,
        match=("Configured benchmark workflow identifiers must be unique"),
    ):
        asyncio.run(
            compare_configured_benchmarks(
                runtime=create_runtime(),
                workflow_ids=(
                    CORRECT_WORKFLOW_ID,
                    CORRECT_WORKFLOW_ID,
                ),
                dataset=create_dataset(),
                output_name="classification",
                scoring_policy=create_policy(),
            )
        )
