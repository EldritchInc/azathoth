"""End-to-end workflow execution across multiple OpenRouter models."""

import asyncio
import json
from uuid import UUID

import httpx
from pydantic import SecretStr

from azathoth.context import Context
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelPricing,
    ModelRequirements,
    OpenRouterConfiguration,
    OpenRouterModelRegistryLoader,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

CHEAP_STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRUCTURED_STEP_ID = UUID("33333333-3333-3333-3333-333333333333")

CHEAP_STRATEGY_ID = UUID("44444444-4444-4444-4444-444444444444")
STRUCTURED_STRATEGY_ID = UUID("55555555-5555-5555-5555-555555555555")

CHEAP_MODEL = "example/cheap-model"
STRUCTURED_MODEL = "example/structured-model"

CHEAP_IDENTIFIER = f"openrouter/{CHEAP_MODEL}"
STRUCTURED_IDENTIFIER = f"openrouter/{STRUCTURED_MODEL}"


def create_catalog() -> ModelCatalog:
    """Create OpenRouter models with intentionally distinct eligibility."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="openrouter",
                model=CHEAP_MODEL,
                display_name="Cheap Model",
                context_window_tokens=8_192,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=0.1,
                    output_usd_per_million_tokens=0.1,
                ),
            ),
            ModelMetadata(
                provider="openrouter",
                model=STRUCTURED_MODEL,
                display_name="Structured Model",
                capabilities=frozenset(
                    {
                        ModelCapability.STRUCTURED_OUTPUT,
                    }
                ),
                context_window_tokens=32_768,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=1.0,
                    output_usd_per_million_tokens=1.0,
                ),
            ),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow whose steps require different model classes."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Heterogeneous OpenRouter workflow",
            description=(
                "Execute two workflow steps using independently selected OpenRouter models."
            ),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=CHEAP_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=CHEAP_STRATEGY_ID,
                        name="cheap classification",
                        description=("Perform an inexpensive classification."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify this request cheaply.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(
                            maximum_input_usd_per_million_tokens=0.2,
                            maximum_output_usd_per_million_tokens=0.2,
                            require_known_pricing=True,
                        )
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="cheap_classification",
                    ),
                ),
            ),
            WorkflowStepSpecification(
                id=STRUCTURED_STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRUCTURED_STRATEGY_ID,
                        name="structured classification",
                        description=("Perform a structured-output-capable classification."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify this request with structured output.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(
                            required_capabilities=frozenset(
                                {
                                    ModelCapability.STRUCTURED_OUTPUT,
                                }
                            ),
                        )
                    ),
                ),
                depends_on=(CHEAP_STEP_ID,),
                outputs=(
                    WorkflowValueBinding(
                        name="structured_classification",
                    ),
                ),
            ),
        ),
    )


def create_transport() -> httpx.MockTransport:
    """Create deterministic responses for each configured OpenRouter model."""

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(request.content.decode())

        model = payload["model"]

        if model == CHEAP_MODEL:
            return httpx.Response(
                200,
                json={
                    "model": CHEAP_MODEL,
                    "choices": [
                        {
                            "message": {
                                "content": "cheap-positive",
                            },
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 1,
                        "total_tokens": 5,
                        "cost": 0.000001,
                    },
                },
            )

        if model == STRUCTURED_MODEL:
            return httpx.Response(
                200,
                json={
                    "model": STRUCTURED_MODEL,
                    "choices": [
                        {
                            "message": {
                                "content": "structured-positive",
                            },
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 1,
                        "total_tokens": 6,
                        "cost": 0.00001,
                    },
                },
            )

        raise AssertionError(f"Unexpected OpenRouter model {model!r}.")

    return httpx.MockTransport(handler)


def test_workflow_executes_different_openrouter_models_per_step() -> None:
    catalog = create_catalog()

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=registry,
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.succeeded
    assert len(run.steps) == 2

    cheap_step = run.steps[0]
    structured_step = run.steps[1]

    assert cheap_step.step_id == CHEAP_STEP_ID
    assert cheap_step.execution is not None
    assert cheap_step.execution.output == "cheap-positive"
    assert cheap_step.execution.metrics is not None
    assert cheap_step.execution.metrics.provider == "openrouter"
    assert cheap_step.execution.metrics.model == CHEAP_MODEL

    assert structured_step.step_id == STRUCTURED_STEP_ID
    assert structured_step.execution is not None
    assert structured_step.execution.output == "structured-positive"
    assert structured_step.execution.metrics is not None
    assert structured_step.execution.metrics.provider == "openrouter"
    assert structured_step.execution.metrics.model == STRUCTURED_MODEL


def test_workflow_model_requirements_select_distinct_openrouter_models() -> None:
    catalog = create_catalog()

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=registry,
    )

    assert len(candidate.steps) == 2

    cheap_strategy = candidate.steps[0].strategy
    structured_strategy = candidate.steps[1].strategy

    assert isinstance(
        cheap_strategy,
        PromptStrategy,
    )
    assert isinstance(
        structured_strategy,
        PromptStrategy,
    )

    assert cheap_strategy.model_binding is not None
    assert cheap_strategy.model_binding.identifier == CHEAP_IDENTIFIER

    assert structured_strategy.model_binding is not None
    assert structured_strategy.model_binding.identifier == STRUCTURED_IDENTIFIER


def test_workflow_preserves_outputs_from_distinct_openrouter_models() -> None:
    catalog = create_catalog()

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=registry,
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    cheap_values = run.values_named("cheap_classification")

    structured_values = run.values_named("structured_classification")

    assert len(cheap_values) == 1
    assert cheap_values[0].producer_step_id == CHEAP_STEP_ID
    assert cheap_values[0].value == "cheap-positive"

    assert len(structured_values) == 1
    assert structured_values[0].producer_step_id == STRUCTURED_STEP_ID
    assert structured_values[0].value == "structured-positive"


def test_workflow_records_independent_openrouter_usage_per_step() -> None:
    catalog = create_catalog()

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    candidate = generate_workflow_candidate(
        specification=create_workflow(),
        catalog=catalog,
        registry=registry,
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    cheap_execution = run.steps[0].execution
    structured_execution = run.steps[1].execution

    assert cheap_execution is not None
    assert structured_execution is not None

    cheap_metrics = cheap_execution.metrics
    structured_metrics = structured_execution.metrics

    assert cheap_metrics is not None
    assert structured_metrics is not None

    assert cheap_metrics.model == CHEAP_MODEL
    assert cheap_metrics.prompt_tokens == 4
    assert cheap_metrics.completion_tokens == 1
    assert cheap_metrics.total_tokens == 5
    assert cheap_metrics.estimated_cost_usd == 0.000001

    assert structured_metrics.model == STRUCTURED_MODEL
    assert structured_metrics.prompt_tokens == 5
    assert structured_metrics.completion_tokens == 1
    assert structured_metrics.total_tokens == 6
    assert structured_metrics.estimated_cost_usd == 0.00001
