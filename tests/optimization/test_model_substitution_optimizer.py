"""Tests for the reference model-substitution workflow optimizer."""

from uuid import UUID

import pytest

from azathoth.optimization import (
    ModelSubstitutionWorkflowOptimizer,
    WorkflowOptimizationResult,
    WorkflowOptimizer,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPricing,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    RankedWorkflow,
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowExperimentResult,
    WorkflowMetadata,
    WorkflowRanking,
    WorkflowScorecard,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_WORKFLOW_ID = UUID("22222222-2222-2222-2222-222222222222")

STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")

EXPENSIVE_MODEL = "example/expensive"
CHEAPER_MODEL = "example/cheaper"
CHEAPEST_MODEL = "example/cheapest"

EXPENSIVE_IDENTIFIER = f"test/{EXPENSIVE_MODEL}"
CHEAPER_IDENTIFIER = f"test/{CHEAPER_MODEL}"
CHEAPEST_IDENTIFIER = f"test/{CHEAPEST_MODEL}"


def create_model(
    *,
    model: str,
    input_price: float,
    output_price: float,
) -> ModelMetadata:
    """Create deterministic model metadata."""

    return ModelMetadata(
        provider="test",
        model=model,
        display_name=model,
        context_window_tokens=32_768,
        pricing=ModelPricing(
            input_usd_per_million_tokens=input_price,
            output_usd_per_million_tokens=output_price,
        ),
    )


def create_model_catalog() -> ModelCatalog:
    """Create an ordered model catalog with decreasing prices."""

    return ModelCatalog(
        models=(
            create_model(
                model=EXPENSIVE_MODEL,
                input_price=10.0,
                output_price=20.0,
            ),
            create_model(
                model=CHEAPER_MODEL,
                input_price=5.0,
                output_price=10.0,
            ),
            create_model(
                model=CHEAPEST_MODEL,
                input_price=1.0,
                output_price=2.0,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable implementations for configured test models."""

    return LanguageModelRegistry(
        models={
            EXPENSIVE_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model=EXPENSIVE_MODEL,
                response_text="success",
            ),
            CHEAPER_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model=CHEAPER_MODEL,
                response_text="success",
            ),
            CHEAPEST_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model=CHEAPEST_MODEL,
                response_text="success",
            ),
        }
    )


def create_workflow(
    *,
    workflow_id: UUID = WORKFLOW_ID,
) -> WorkflowSpecification:
    """Create a deterministic prompt-backed workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=workflow_id,
            name="model substitution workflow",
            description=("Exercise the reference model substitution optimizer."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="classify",
                        description="Classify one request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
            ),
        ),
    )


def create_candidate(
    *,
    specification: WorkflowSpecification,
    model_identifier: str,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Create one workflow candidate bound to an exact model."""

    model = catalog.get(model_identifier)

    assert model is not None

    return generate_workflow_candidate(
        specification=specification,
        catalog=ModelCatalog(models=(model,)),
        registry=registry,
    )


def create_experiment() -> WorkflowExperimentResult:
    """Create deterministic experiment evidence."""

    scorecard = WorkflowScorecard(
        quality_score=1.0,
        reliability_score=1.0,
        latency_score=1.0,
        cost_score=0.5,
        overall_score=0.875,
        rationale="Existing candidate passed.",
    )

    return WorkflowExperimentResult(
        scorecards=(scorecard,),
        ranking=WorkflowRanking(
            entries=(
                RankedWorkflow(
                    rank=1,
                    scorecard=scorecard,
                ),
            )
        ),
    )


def create_optimizer(
    *,
    workflow: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> ModelSubstitutionWorkflowOptimizer:
    """Create the reference optimizer with deterministic dependencies."""

    return ModelSubstitutionWorkflowOptimizer(
        workflows=WorkflowCatalog(specifications=(workflow,)),
        models=catalog,
        registry=registry,
    )


def model_identifier(
    candidate: WorkflowCandidate,
) -> str:
    """Return the model bound to the candidate prompt strategy."""

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def test_model_substitution_optimizer_satisfies_protocol() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    optimizer: WorkflowOptimizer = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = optimizer.optimize(
        experiment=create_experiment(),
        candidates=(candidate,),
        generation=1,
    )

    assert isinstance(
        result,
        WorkflowOptimizationResult,
    )


def test_model_substitution_optimizer_preserves_original_candidate() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    ).optimize(
        experiment=create_experiment(),
        candidates=(candidate,),
        generation=1,
    )

    assert result.candidates[0] is candidate


def test_model_substitution_optimizer_adds_cheaper_candidates() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    ).optimize(
        experiment=create_experiment(),
        candidates=(candidate,),
        generation=1,
    )

    assert tuple(model_identifier(candidate) for candidate in result.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )


def test_model_substitution_optimizer_preserves_experiment_evidence() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    experiment = create_experiment()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    ).optimize(
        experiment=experiment,
        candidates=(candidate,),
        generation=3,
    )

    assert result.generation == 3
    assert result.previous_experiment is experiment


def test_model_substitution_optimizer_returns_baseline_when_no_cheaper_model_exists() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=CHEAPEST_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    ).optimize(
        experiment=create_experiment(),
        candidates=(candidate,),
        generation=1,
    )

    assert result.candidates == (candidate,)


def test_model_substitution_optimizer_deduplicates_expanded_candidates() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    expensive = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    cheaper = create_candidate(
        specification=workflow,
        model_identifier=CHEAPER_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    result = create_optimizer(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    ).optimize(
        experiment=create_experiment(),
        candidates=(
            expensive,
            cheaper,
        ),
        generation=1,
    )

    assert tuple(model_identifier(candidate) for candidate in result.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )


def test_model_substitution_optimizer_requires_workflow_specification() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    optimizer = ModelSubstitutionWorkflowOptimizer(
        workflows=WorkflowCatalog(),
        models=catalog,
        registry=registry,
    )

    with pytest.raises(
        ValueError,
        match=("Workflow candidate must reference a configured workflow specification"),
    ):
        optimizer.optimize(
            experiment=create_experiment(),
            candidates=(candidate,),
            generation=1,
        )


def test_model_substitution_optimizer_resolves_specification_by_workflow_id() -> None:
    workflow = create_workflow()
    unrelated = create_workflow(workflow_id=SECOND_WORKFLOW_ID)

    catalog = create_model_catalog()
    registry = create_registry()

    candidate = create_candidate(
        specification=workflow,
        model_identifier=EXPENSIVE_IDENTIFIER,
        catalog=catalog,
        registry=registry,
    )

    optimizer = ModelSubstitutionWorkflowOptimizer(
        workflows=WorkflowCatalog(
            specifications=(
                unrelated,
                workflow,
            )
        ),
        models=catalog,
        registry=registry,
    )

    result = optimizer.optimize(
        experiment=create_experiment(),
        candidates=(candidate,),
        generation=1,
    )

    assert tuple(model_identifier(candidate) for candidate in result.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )
