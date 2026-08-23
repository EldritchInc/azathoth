"""Tests for running configured workflows through the CLI."""

from uuid import UUID

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import run_workflow
from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowCatalog,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

UNKNOWN_WORKFLOW_ID = UUID("99999999-9999-9999-9999-999999999999")

STEP_ID = UUID("22222222-2222-2222-2222-222222222222")

STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

MODEL_IDENTIFIER = "test/example"


def create_workflow() -> WorkflowSpecification:
    """Create one workflow for CLI execution."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="CLI execution",
            description=("Exercise workflow execution through the CLI."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="CLI prompt",
                        description=("Execute one deterministic CLI prompt."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return success.",
                    ),
                    model_requirements=ModelRequirements(),
                ),
            ),
        ),
    )


def create_runtime() -> AzathothRuntime:
    """Create one deterministic executable runtime."""

    return AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="test",
                    model="example",
                    display_name="Example Model",
                    context_window_tokens=8_192,
                ),
            )
        ),
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


def configure_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: AzathothRuntime,
) -> None:
    """Replace CLI runtime bootstrap with one deterministic runtime."""

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )


def test_workflow_run_executes_configured_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_runtime(
        monkeypatch,
        create_runtime(),
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (f"Workflow {WORKFLOW_ID} succeeded.\n")

    assert captured.err == ""


def test_workflow_run_reports_unknown_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_runtime(
        monkeypatch,
        create_runtime(),
    )

    result = run_workflow(UNKNOWN_WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Workflow {UNKNOWN_WORKFLOW_ID} is not configured.\n")


def test_workflow_run_reports_non_executable_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = AzathothRuntime(
        workflows=WorkflowCatalog(specifications=(create_workflow(),)),
        models=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="test",
                    model="example",
                    display_name="Example Model",
                    context_window_tokens=8_192,
                ),
            )
        ),
        language_models=LanguageModelRegistry(),
    )

    configure_runtime(
        monkeypatch,
        runtime,
    )

    result = run_workflow(WORKFLOW_ID)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert (
        "No executable prompt candidate could be generated "
        f"for workflow step {STEP_ID}." in captured.err
    )
