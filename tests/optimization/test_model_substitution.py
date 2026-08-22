"""Tests for mechanical workflow model substitution."""

from uuid import UUID

from azathoth.optimization import generate_model_substitutions
from azathoth.prompting import PromptStrategy, PromptStrategySpec
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelPricing,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

EXPENSIVE_MODEL = "example/expensive"
CHEAPER_MODEL = "example/cheaper"
CHEAPEST_MODEL = "example/cheapest"
INCOMPATIBLE_MODEL = "example/incompatible"
TRADEOFF_MODEL = "example/tradeoff"

EXPENSIVE_IDENTIFIER = f"test/{EXPENSIVE_MODEL}"
CHEAPER_IDENTIFIER = f"test/{CHEAPER_MODEL}"
CHEAPEST_IDENTIFIER = f"test/{CHEAPEST_MODEL}"
INCOMPATIBLE_IDENTIFIER = f"test/{INCOMPATIBLE_MODEL}"
TRADEOFF_IDENTIFIER = f"test/{TRADEOFF_MODEL}"


def create_model(
    *,
    model: str,
    input_price: float,
    output_price: float,
    structured_output: bool = True,
) -> ModelMetadata:
    """Create deterministic model metadata."""

    capabilities = (
        frozenset(
            {
                ModelCapability.STRUCTURED_OUTPUT,
            }
        )
        if structured_output
        else frozenset()
    )

    return ModelMetadata(
        provider="test",
        model=model,
        display_name=model,
        capabilities=capabilities,
        context_window_tokens=32_768,
        pricing=ModelPricing(
            input_usd_per_million_tokens=input_price,
            output_usd_per_million_tokens=output_price,
        ),
    )


def create_catalog() -> ModelCatalog:
    """Create models spanning useful substitution cases."""

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
                output_price=20.0,
            ),
            create_model(
                model=CHEAPEST_MODEL,
                input_price=2.0,
                output_price=4.0,
            ),
            create_model(
                model=INCOMPATIBLE_MODEL,
                input_price=1.0,
                output_price=1.0,
                structured_output=False,
            ),
            create_model(
                model=TRADEOFF_MODEL,
                input_price=1.0,
                output_price=30.0,
            ),
        )
    )


def create_registry() -> LanguageModelRegistry:
    """Create executable implementations for every configured model."""

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
            INCOMPATIBLE_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model=INCOMPATIBLE_MODEL,
                response_text="success",
            ),
            TRADEOFF_IDENTIFIER: DeterministicLanguageModel(
                provider="test",
                model=TRADEOFF_MODEL,
                response_text="success",
            ),
        }
    )


def create_workflow() -> WorkflowSpecification:
    """Create a prompt-backed workflow requiring structured output."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="model substitution workflow",
            description=("Exercise deterministic cheaper-model substitution."),
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
                    model_requirements=ModelRequirements(
                        required_capabilities=frozenset(
                            {
                                ModelCapability.STRUCTURED_OUTPUT,
                            }
                        ),
                    ),
                ),
            ),
        ),
    )


def create_expensive_candidate(
    *,
    workflow: WorkflowSpecification,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Create a candidate bound only to the expensive model."""

    catalog = create_catalog()

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
    """Return the model identifier bound to the candidate prompt step."""

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        PromptStrategy,
    )

    assert strategy.model_binding is not None

    return strategy.model_binding.identifier


def test_model_substitution_generates_strictly_cheaper_candidates() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    assert tuple(model_identifier(substitution) for substitution in substitutions) == (
        CHEAPER_IDENTIFIER,
        CHEAPEST_IDENTIFIER,
    )


def test_model_substitution_preserves_workflow_identity() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    assert substitutions

    assert all(substitution.metadata == candidate.metadata for substitution in substitutions)

    assert all(substitution.steps[0].id == STEP_ID for substitution in substitutions)


def test_model_substitution_regenerates_prompt_strategy_identity() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    original_strategy = candidate.steps[0].strategy

    assert isinstance(
        original_strategy,
        PromptStrategy,
    )

    replacement_strategy = substitutions[0].steps[0].strategy

    assert isinstance(
        replacement_strategy,
        PromptStrategy,
    )

    assert replacement_strategy.metadata.id != original_strategy.metadata.id

    assert replacement_strategy.model_binding is not None

    assert replacement_strategy.model_binding.identifier == CHEAPER_IDENTIFIER


def test_model_substitution_rejects_capability_incompatible_models() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    identifiers = tuple(model_identifier(substitution) for substitution in substitutions)

    assert INCOMPATIBLE_IDENTIFIER not in identifiers


def test_model_substitution_rejects_price_tradeoffs() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    identifiers = tuple(model_identifier(substitution) for substitution in substitutions)

    assert TRADEOFF_IDENTIFIER not in identifiers


def test_model_substitution_requires_executable_target_model() -> None:
    workflow = create_workflow()

    full_registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=full_registry,
    )

    expensive_model = full_registry.get(EXPENSIVE_IDENTIFIER)

    assert expensive_model is not None

    registry = LanguageModelRegistry(
        models={
            EXPENSIVE_IDENTIFIER: expensive_model,
        }
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=create_catalog(),
        registry=registry,
    )

    assert substitutions == ()


def test_model_substitution_returns_empty_when_no_cheaper_model_exists() -> None:
    workflow = create_workflow()
    registry = create_registry()

    catalog = create_catalog()

    cheapest = catalog.get(CHEAPEST_IDENTIFIER)

    assert cheapest is not None

    candidate = generate_workflow_candidate(
        specification=workflow,
        catalog=ModelCatalog(models=(cheapest,)),
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=catalog,
        registry=registry,
    )

    assert substitutions == ()


def test_model_substitution_rejects_mismatched_workflow_identity() -> None:
    workflow = create_workflow()
    registry = create_registry()

    candidate = create_expensive_candidate(
        workflow=workflow,
        registry=registry,
    )

    different_workflow = workflow.model_copy(
        update={
            "metadata": workflow.metadata.model_copy(
                update={"id": UUID("44444444-4444-4444-4444-444444444444")}
            )
        }
    )

    try:
        generate_model_substitutions(
            specification=different_workflow,
            candidate=candidate,
            catalog=create_catalog(),
            registry=registry,
        )
    except ValueError as exc:
        assert str(exc) == ("Workflow specification and candidate must share an identifier.")
    else:
        raise AssertionError("Expected mismatched workflow identity to fail.")
