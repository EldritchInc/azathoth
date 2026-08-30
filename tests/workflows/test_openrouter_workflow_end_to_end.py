"""End-to-end tests for OpenRouter-backed workflow execution."""

import asyncio
from typing import Any
from uuid import UUID

import httpx
from pydantic import SecretStr

from azathoth.context import Context
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    OpenRouterConfiguration,
    OpenRouterLanguageModel,
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
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL_IDENTIFIER = "openrouter/openai/gpt-test"


def create_configuration() -> OpenRouterConfiguration:
    """Create deterministic OpenRouter configuration."""

    return OpenRouterConfiguration(
        api_key=SecretStr("test-openrouter-key"),
        base_url="https://openrouter.test/api/v1",
        timeout_seconds=10.0,
    )


def create_response() -> dict[str, Any]:
    """Create a deterministic OpenRouter response."""

    return {
        "id": "generation-1",
        "model": "openai/gpt-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "positive",
                },
            },
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 1,
            "total_tokens": 8,
            "cost": 0.000012,
        },
    }


def create_language_model() -> OpenRouterLanguageModel:
    """Create an OpenRouter model backed by a mocked transport."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=create_response(),
            request=request,
        )

    return OpenRouterLanguageModel(
        create_configuration(),
        "openai/gpt-test",
        transport=httpx.MockTransport(handler),
    )


def create_specification() -> WorkflowSpecification:
    """Create a deterministic model-backed workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Classify sentiment",
            description="Classify one text input using a language model.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify sentiment",
                        description="Return the sentiment classification.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify this text as positive or negative.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
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


def create_catalog() -> ModelCatalog:
    """Create a catalog containing one eligible OpenRouter model."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider="openrouter",
                model="openai/gpt-test",
                display_name="OpenRouter Test Model",
                context_window_tokens=8_192,
            ),
        ),
    )


def create_registry() -> LanguageModelRegistry:
    """Create a registry containing one executable OpenRouter model."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: create_language_model(),
        },
    )


def test_openrouter_backed_workflow_executes_end_to_end() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.succeeded
    assert len(run.steps) == 1

    step = run.steps[0]

    assert step.execution is not None
    assert step.execution.output == "positive"
    assert step.execution.metrics is not None
    assert step.execution.metrics.provider == "openrouter"
    assert step.execution.metrics.model == "openai/gpt-test"


def test_openrouter_backed_workflow_records_provider_metrics() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.metrics is not None
    assert execution.metrics.prompt_tokens == 7
    assert execution.metrics.completion_tokens == 1
    assert execution.metrics.total_tokens == 8
    assert execution.metrics.latency_ms is not None
    assert execution.metrics.latency_ms >= 0
    assert execution.metrics.estimated_cost_usd == 0.000012


def test_openrouter_backed_workflow_exports_model_output() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    assert run.values_named("classification") == (run.steps[0].values[0],)
    assert run.steps[0].values[0].name == "classification"
    assert run.steps[0].values[0].value == "positive"
    assert run.steps[0].values[0].producer_step_id == STEP_ID


def test_openrouter_backed_workflow_preserves_model_binding() -> None:
    candidate = generate_workflow_candidate(
        specification=create_specification(),
        catalog=create_catalog(),
        registry=create_registry(),
    )

    strategy = candidate.steps[0].strategy

    assert strategy.metadata.name == ("Classify sentiment [openrouter/openai/gpt-test]")

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.metrics is not None

    reported_identifier = f"{execution.metrics.provider}/{execution.metrics.model}"

    assert reported_identifier == MODEL_IDENTIFIER


def test_openrouter_backed_workflow_round_trips() -> None:
    specification = create_specification()

    restored_specification = WorkflowSpecification.model_validate_json(
        specification.model_dump_json(),
    )

    candidate = generate_workflow_candidate(
        specification=restored_specification,
        catalog=create_catalog(),
        registry=create_registry(),
    )

    run = asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )

    restored_run = type(run).model_validate_json(
        run.model_dump_json(),
    )

    assert restored_specification == specification
    assert restored_run == run
    assert restored_run.succeeded
    assert restored_run.values_named("classification")[0].value == "positive"
