"""End-to-end workflow execution from durable model configuration."""

import asyncio
import json
from pathlib import Path
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
    ModelCatalogLoader,
    ModelMetadata,
    ModelPricing,
    ModelRequirements,
    OpenRouterConfiguration,
    OpenRouterModelRegistryLoader,
    Prompt,
    SQLiteModelRepository,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowCatalogLoader,
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


def create_cheap_model() -> ModelMetadata:
    """Create model metadata eligible only for the inexpensive step."""

    return ModelMetadata(
        provider="openrouter",
        model=CHEAP_MODEL,
        display_name="Cheap Model",
        context_window_tokens=8_192,
        pricing=ModelPricing(
            input_usd_per_million_tokens=0.1,
            output_usd_per_million_tokens=0.1,
        ),
    )


def create_structured_model() -> ModelMetadata:
    """Create model metadata eligible for structured-output workloads."""

    return ModelMetadata(
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
    )


def create_workflow() -> WorkflowSpecification:
    """Create a workflow requiring two different model classes."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Durable heterogeneous model workflow",
            description=("Resolve different prompt steps from a persisted model catalog."),
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
    """Create deterministic OpenRouter responses for persisted models."""

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


def persist_configuration(
    *,
    model_database: Path,
    workflow_database: Path,
) -> None:
    """Persist model metadata and workflow specification."""

    model_repository = SQLiteModelRepository(model_database)

    model_repository.save(create_cheap_model())
    model_repository.save(create_structured_model())

    SQLiteWorkflowRepository(workflow_database).save(create_workflow())


def reconstruct_model_catalog(
    database: Path,
) -> ModelCatalog:
    """Reconstruct configured model metadata after process restart."""

    return ModelCatalogLoader(SQLiteModelRepository(database)).load_catalog()


def reconstruct_workflow(
    database: Path,
) -> WorkflowSpecification:
    """Reconstruct the durable workflow after process restart."""

    catalog = WorkflowCatalogLoader(SQLiteWorkflowRepository(database)).load_catalog()

    workflow = catalog.get(WORKFLOW_ID)

    assert workflow is not None

    return workflow


def test_durable_model_catalog_reconstructs_complete_model_universe(
    tmp_path: Path,
) -> None:
    model_database = tmp_path / "models.db"
    workflow_database = tmp_path / "workflows.db"

    persist_configuration(
        model_database=model_database,
        workflow_database=workflow_database,
    )

    catalog = reconstruct_model_catalog(model_database)

    assert catalog.identifiers == (
        CHEAP_IDENTIFIER,
        STRUCTURED_IDENTIFIER,
    )

    cheap = catalog.get(CHEAP_IDENTIFIER)
    structured = catalog.get(STRUCTURED_IDENTIFIER)

    assert cheap == create_cheap_model()
    assert structured == create_structured_model()

    assert cheap is not None
    assert structured is not None

    assert cheap.pricing is not None
    assert cheap.pricing.input_usd_per_million_tokens == 0.1

    assert ModelCapability.STRUCTURED_OUTPUT not in cheap.capabilities

    assert ModelCapability.STRUCTURED_OUTPUT in structured.capabilities


def test_reconstructed_model_catalog_assembles_openrouter_runtime(
    tmp_path: Path,
) -> None:
    model_database = tmp_path / "models.db"
    workflow_database = tmp_path / "workflows.db"

    persist_configuration(
        model_database=model_database,
        workflow_database=workflow_database,
    )

    catalog = reconstruct_model_catalog(model_database)

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    assert registry.identifiers == (
        CHEAP_IDENTIFIER,
        STRUCTURED_IDENTIFIER,
    )

    assert registry.get(CHEAP_IDENTIFIER) is not None

    assert registry.get(STRUCTURED_IDENTIFIER) is not None


def test_reconstructed_workflow_resolves_models_from_durable_catalog(
    tmp_path: Path,
) -> None:
    model_database = tmp_path / "models.db"
    workflow_database = tmp_path / "workflows.db"

    persist_configuration(
        model_database=model_database,
        workflow_database=workflow_database,
    )

    catalog = reconstruct_model_catalog(model_database)

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    workflow = reconstruct_workflow(workflow_database)

    candidate = generate_workflow_candidate(
        specification=workflow,
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
    assert structured_strategy.model_binding is not None

    assert cheap_strategy.model_binding.identifier == CHEAP_IDENTIFIER

    assert structured_strategy.model_binding.identifier == STRUCTURED_IDENTIFIER


def test_durable_workflow_executes_heterogeneous_persisted_models(
    tmp_path: Path,
) -> None:
    model_database = tmp_path / "models.db"
    workflow_database = tmp_path / "workflows.db"

    persist_configuration(
        model_database=model_database,
        workflow_database=workflow_database,
    )

    catalog = reconstruct_model_catalog(model_database)

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    workflow = reconstruct_workflow(workflow_database)

    candidate = generate_workflow_candidate(
        specification=workflow,
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
    assert run.workflow == workflow.metadata

    assert len(run.steps) == 2

    cheap_execution = run.steps[0].execution
    structured_execution = run.steps[1].execution

    assert cheap_execution is not None
    assert structured_execution is not None

    assert cheap_execution.output == "cheap-positive"
    assert structured_execution.output == "structured-positive"

    cheap_metrics = cheap_execution.metrics
    structured_metrics = structured_execution.metrics

    assert cheap_metrics is not None
    assert structured_metrics is not None

    assert cheap_metrics.provider == "openrouter"
    assert cheap_metrics.model == CHEAP_MODEL

    assert structured_metrics.provider == "openrouter"
    assert structured_metrics.model == STRUCTURED_MODEL


def test_durable_model_selection_preserves_per_step_usage_evidence(
    tmp_path: Path,
) -> None:
    model_database = tmp_path / "models.db"
    workflow_database = tmp_path / "workflows.db"

    persist_configuration(
        model_database=model_database,
        workflow_database=workflow_database,
    )

    catalog = reconstruct_model_catalog(model_database)

    registry = OpenRouterModelRegistryLoader(
        OpenRouterConfiguration(
            api_key=SecretStr("test-key"),
        ),
        transport=create_transport(),
    ).load_registry(catalog)

    candidate = generate_workflow_candidate(
        specification=reconstruct_workflow(workflow_database),
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
