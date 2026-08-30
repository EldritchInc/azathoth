"""Tests for configured workflow execution application services."""

import asyncio
from uuid import UUID

import pytest

from azathoth.cli import execute_configured_workflow
from azathoth.context import Context, ContextEvent
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.runtime import (
    AzathothRuntime,
    WorkflowNotConfiguredError,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from tests.model_authorization import (
    portfolio_for_catalog,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL_IDENTIFIER = "test/example"


def create_workflow() -> WorkflowSpecification:
    """Create one prompt-backed workflow."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="configured execution",
            description=("Exercise configured workflow execution."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="configured prompt",
                        description=("Execute one deterministic prompt."),
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


def create_runtime() -> AzathothRuntime:
    """Create one executable configured runtime."""

    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="example",
                display_name="Example Model",
                context_window_tokens=8_192,
            ),
        )
    )

    return AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=models,
        portfolio=portfolio_for_catalog(models),
        language_models=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: DeterministicLanguageModel(
                    provider="test",
                    model="example",
                    response_text="success",
                ),
            }
        ),
    )


def test_configured_workflow_execution_generates_and_runs_candidate() -> None:
    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
        )
    )

    assert run.workflow.id == WORKFLOW_ID
    assert run.workflow.name == "configured execution"

    assert run.succeeded
    assert not run.failed

    assert len(run.steps) == 1

    execution = run.steps[0].execution

    assert execution is not None
    assert execution.output == "success"


def test_configured_workflow_execution_uses_empty_context_by_default() -> None:
    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
        )
    )

    assert run.initial_context == Context()


def test_configured_workflow_execution_preserves_supplied_context() -> None:
    context = Context(
        events=(
            ContextEvent(
                event_type="request.received",
                payload={
                    "text": "Execute the configured workflow.",
                },
                producer="test",
            ),
        )
    )

    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            context=context,
        )
    )

    assert run.initial_context == context

    assert run.final_context.events[: len(context.events)] == (context.events)


def test_configured_workflow_execution_preserves_unknown_workflow_error() -> None:
    with pytest.raises(
        WorkflowNotConfiguredError,
        match=(f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured"),
    ):
        asyncio.run(
            execute_configured_workflow(
                runtime=create_runtime(),
                workflow_id=UNKNOWN_WORKFLOW_ID,
            )
        )


def test_configured_workflow_execution_preserves_generation_failure() -> None:
    models = ModelCatalog(
        models=(
            ModelMetadata(
                provider="test",
                model="example",
                display_name="Example Model",
                context_window_tokens=8_192,
            ),
        )
    )

    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=models,
        portfolio=portfolio_for_catalog(models),
        language_models=LanguageModelRegistry(),
    )

    with pytest.raises(
        WorkflowGenerationError,
        match=("No executable prompt candidate could be generated"),
    ):
        asyncio.run(
            execute_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
            )
        )


def test_configured_workflow_execution_accepts_explicit_runner() -> None:
    runner = WorkflowRunner()

    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_runtime(),
            workflow_id=WORKFLOW_ID,
            runner=runner,
        )
    )

    assert run.succeeded
