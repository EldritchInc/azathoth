"""Opt-in live tests for OpenRouter-backed workflow execution."""

import asyncio
import os
from uuid import UUID

import pytest
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
    generate_workflow_candidate,
)

_LIVE_TEST_FLAG = "AZATHOTH_RUN_LIVE_OPENROUTER_TESTS"
_API_KEY_VARIABLE = "OPENROUTER_API_KEY"
_MODEL_VARIABLE = "OPENROUTER_TEST_MODEL"

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


def live_tests_enabled() -> bool:
    """Return whether live OpenRouter testing was explicitly requested."""

    return os.environ.get(_LIVE_TEST_FLAG) == "1"


def require_environment_variable(name: str) -> str:
    """Return a required environment variable for live testing."""

    value = os.environ.get(name)

    if not value:
        pytest.skip(f"{name} is required for live OpenRouter testing.")

    return value


def create_specification() -> WorkflowSpecification:
    """Create a live model-backed workflow specification."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Live sentiment classification",
            description="Execute one classification workflow through OpenRouter.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify sentiment",
                        description="Return exactly positive or negative.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=(
                            "Classify the sentiment of this text. "
                            "Return exactly positive or negative.\n\n"
                            "Text: I absolutely loved this."
                        ),
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


@pytest.mark.skipif(
    not live_tests_enabled(),
    reason=("Live OpenRouter tests require AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1."),
)
def test_openrouter_workflow_executes_live_end_to_end() -> None:
    api_key = require_environment_variable(_API_KEY_VARIABLE)
    model_name = require_environment_variable(_MODEL_VARIABLE)

    model_identifier = f"openrouter/{model_name}"

    catalog = ModelCatalog(
        models=(
            ModelMetadata(
                provider="openrouter",
                model=model_name,
                display_name="Live OpenRouter Test Model",
                context_window_tokens=8_192,
            ),
        ),
    )

    registry = LanguageModelRegistry(
        models={
            model_identifier: OpenRouterLanguageModel(
                OpenRouterConfiguration(
                    api_key=SecretStr(api_key),
                ),
                model_name,
            ),
        },
    )

    candidate = generate_workflow_candidate(
        specification=create_specification(),
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
    assert len(run.steps) == 1

    step = run.steps[0]

    assert step.execution is not None
    assert isinstance(step.execution.output, str)
    assert step.execution.output.strip().lower() == "positive"

    assert step.execution.metrics is not None

    metrics = step.execution.metrics

    assert metrics.provider == "openrouter"
    assert metrics.model == model_name

    assert metrics.prompt_tokens is not None
    assert metrics.prompt_tokens > 0

    assert metrics.completion_tokens is not None
    assert metrics.completion_tokens > 0

    assert metrics.total_tokens is not None
    assert metrics.total_tokens > 0

    assert metrics.latency_ms is not None
    assert metrics.latency_ms >= 0

    assert metrics.estimated_cost_usd is not None
    assert metrics.estimated_cost_usd >= 0.0

    classification_values = run.values_named("classification")

    assert len(classification_values) == 1

    classification = classification_values[0]

    assert isinstance(classification.value, str)
    assert classification.value.strip().lower() == "positive"
