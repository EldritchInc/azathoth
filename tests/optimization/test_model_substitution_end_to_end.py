"""End-to-end empirical optimization through model substitution."""

import asyncio
from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.optimization import (
    ModelSubstitutionWorkflowOptimizer,
    WorkflowOptimizationSessionRunner,
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
    ModelPricing,
    ModelRequirements,
    ModelResponse,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowExperimentRunner,
    WorkflowMetadata,
    WorkflowScorer,
    WorkflowScoringPolicy,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    generate_workflow_candidate,
    portfolio_for_catalog,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

EXPENSIVE_MODEL = "expensive"
CHEAPER_MODEL = "cheaper"
CHEAPEST_MODEL = "cheapest"

EXPENSIVE_IDENTIFIER = f"test/{EXPENSIVE_MODEL}"
CHEAPER_IDENTIFIER = f"test/{CHEAPER_MODEL}"
CHEAPEST_IDENTIFIER = f"test/{CHEAPEST_MODEL}"

EXPENSIVE_COST = 0.010
CHEAPER_COST = 0.005
CHEAPEST_COST = 0.001


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
            provider="test",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=(prompt_tokens + completion_tokens),
            latency_ms=0,
            estimated_cost_usd=self._estimated_cost_usd,
        )


def create_model(
    *,
    model: str,
    input_price: float,
    output_price: float,
) -> ModelMetadata:
    """Create configured model metadata."""

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
    """Create an ordered catalog with strictly decreasing prices."""

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
    """Create deterministic models with distinct execution costs."""

    return LanguageModelRegistry(
        models={
            EXPENSIVE_IDENTIFIER: CostedDeterministicLanguageModel(
                model=EXPENSIVE_MODEL,
                estimated_cost_usd=EXPENSIVE_COST,
            ),
            CHEAPER_IDENTIFIER: CostedDeterministicLanguageModel(
                model=CHEAPER_MODEL,
                estimated_cost_usd=CHEAPER_COST,
            ),
            CHEAPEST_IDENTIFIER: CostedDeterministicLanguageModel(
                model=CHEAPEST_MODEL,
                estimated_cost_usd=CHEAPEST_COST,
            ),
        }
    )


def create_workflow() -> WorkflowSpecification:
    """Create the model-backed workflow to optimize."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="empirical model cost optimization",
            description=("Demonstrate empirical improvement through cheaper model substitution."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="return success",
                        description=("Return the expected deterministic result."),
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


def create_initial_candidate(
    *,
    workflow: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Create an initial workflow bound only to the expensive model."""

    expensive = catalog.get(EXPENSIVE_IDENTIFIER)

    assert expensive is not None

    return generate_workflow_candidate(
        specification=workflow,
        catalog=ModelCatalog(models=(expensive,)),
        registry=registry,
    )


def model_identifier(
    candidate: WorkflowCandidate,
) -> str:
    """Return the model bound to the workflow's prompt step."""

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def create_experiment_runner() -> WorkflowExperimentRunner:
    """Create scoring that makes execution cost empirically visible."""

    return WorkflowExperimentRunner(
        scorer=WorkflowScorer(
            policy=WorkflowScoringPolicy(
                target_latency_seconds=1_000.0,
                target_cost_usd=CHEAPEST_COST,
            )
        )
    )


def test_model_substitution_session_generates_cheaper_population() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    initial = create_initial_candidate(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=create_experiment_runner(),
            optimizer=ModelSubstitutionWorkflowOptimizer(
                workflows=WorkflowCatalog(specifications=(workflow,)),
                models=catalog,
                portfolio=portfolio_for_catalog(catalog),
                registry=registry,
            ),
        ).run(
            initial_candidates=(initial,),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    assert len(session.generations) == 2

    first_generation = session.generations[0]

    assert tuple(model_identifier(candidate) for candidate in first_generation.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )


def test_model_substitution_session_preserves_passing_quality() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    initial = create_initial_candidate(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=create_experiment_runner(),
            optimizer=ModelSubstitutionWorkflowOptimizer(
                workflows=WorkflowCatalog(specifications=(workflow,)),
                models=catalog,
                portfolio=portfolio_for_catalog(catalog),
                registry=registry,
            ),
        ).run(
            initial_candidates=(initial,),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    first_experiment = session.generations[0].previous_experiment

    second_experiment = session.generations[1].previous_experiment

    assert len(first_experiment.scorecards) == 1

    assert first_experiment.scorecards[0].quality_score == 1.0

    assert len(second_experiment.scorecards) == 3

    assert all(scorecard.quality_score == 1.0 for scorecard in second_experiment.scorecards)

    assert all(scorecard.reliability_score == 1.0 for scorecard in second_experiment.scorecards)


def test_model_substitution_session_improves_empirical_cost_score() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    initial = create_initial_candidate(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=create_experiment_runner(),
            optimizer=ModelSubstitutionWorkflowOptimizer(
                workflows=WorkflowCatalog(specifications=(workflow,)),
                models=catalog,
                portfolio=portfolio_for_catalog(catalog),
                registry=registry,
            ),
        ).run(
            initial_candidates=(initial,),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    first_experiment = session.generations[0].previous_experiment

    second_experiment = session.generations[1].previous_experiment

    initial_scorecard = first_experiment.scorecards[0]

    optimized_winner = second_experiment.winner

    assert initial_scorecard.quality_score == optimized_winner.quality_score == 1.0

    assert initial_scorecard.reliability_score == optimized_winner.reliability_score == 1.0

    assert optimized_winner.cost_score > initial_scorecard.cost_score

    assert optimized_winner.overall_score > initial_scorecard.overall_score

    assert initial_scorecard.cost_score == 0.1
    assert optimized_winner.cost_score == 1.0


def test_model_substitution_session_ranks_cheapest_passing_execution_first() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    initial = create_initial_candidate(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=create_experiment_runner(),
            optimizer=ModelSubstitutionWorkflowOptimizer(
                workflows=WorkflowCatalog(specifications=(workflow,)),
                models=catalog,
                portfolio=portfolio_for_catalog(catalog),
                registry=registry,
            ),
        ).run(
            initial_candidates=(initial,),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    experiment = session.generations[1].previous_experiment

    assert tuple(scorecard.cost_score for scorecard in experiment.scorecards) == (
        0.1,
        0.2,
        1.0,
    )

    assert experiment.ranking.entries[0].scorecard.cost_score == 1.0

    assert experiment.ranking.entries[1].scorecard.cost_score == 0.2

    assert experiment.ranking.entries[2].scorecard.cost_score == 0.1


def test_model_substitution_session_retains_empirical_baseline() -> None:
    workflow = create_workflow()
    catalog = create_model_catalog()
    registry = create_registry()

    initial = create_initial_candidate(
        workflow=workflow,
        catalog=catalog,
        registry=registry,
    )

    session = asyncio.run(
        WorkflowOptimizationSessionRunner(
            experiment_runner=create_experiment_runner(),
            optimizer=ModelSubstitutionWorkflowOptimizer(
                workflows=WorkflowCatalog(specifications=(workflow,)),
                models=catalog,
                portfolio=portfolio_for_catalog(catalog),
                registry=registry,
            ),
        ).run(
            initial_candidates=(initial,),
            context=Context(),
            evaluator=ExactMatchEvaluator(),
            expected_outcome=ExpectedOutcome(
                description="Return success.",
                value="success",
                comparison=OutcomeComparison.EXACT,
            ),
            max_generations=2,
        )
    )

    second_generation = session.generations[1]

    assert tuple(model_identifier(candidate) for candidate in second_generation.candidates) == (
        EXPENSIVE_IDENTIFIER,
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )
