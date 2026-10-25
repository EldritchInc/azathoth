"""Tests that configured workflow runs record step failures instead of raising."""

import asyncio
from pathlib import Path

import pytest

import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    execute_configured_workflow,
    run_workflow,
)
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.context import Context
from azathoth.execution import (
    ExecutionResult,
    StrategyExecutor,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelResponse,
    Prompt,
)
from azathoth.runtime import AzathothRuntime
from azathoth.strategies import Strategy
from azathoth.workflows import (
    SQLiteWorkflowRunRepository,
    WorkflowCatalog,
    WorkflowRunner,
    WorkflowStepStatus,
)
from tests.cli.test_workflow_run import (
    MODEL_IDENTIFIER,
    STEP_ID,
    WORKFLOW_ID,
    configure_database,
    create_workflow,
)
from tests.model_authorization import (
    portfolio_for_catalog,
)


class FailingLanguageModel:
    """A language model whose every completion fails."""

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Fail the completion."""

        raise RuntimeError("Model exploded.")


class FailingExecutor(StrategyExecutor):
    """A strategy executor whose every execution fails."""

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Fail the execution."""

        raise RuntimeError("Step exploded.")


def create_failing_runtime() -> AzathothRuntime:
    """Create one runtime whose only workflow step always fails."""

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
                MODEL_IDENTIFIER: FailingLanguageModel(),
            }
        ),
    )


def configure_failing_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at an isolated database and one always-failing runtime."""

    database = configure_database(
        monkeypatch,
        tmp_path,
    )

    runtime = create_failing_runtime()

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    return database


def test_configured_execution_returns_failed_run_instead_of_raising() -> None:
    run = asyncio.run(
        execute_configured_workflow(
            runtime=create_failing_runtime(),
            workflow_id=WORKFLOW_ID,
            runner=WorkflowRunner(
                executor=FailingExecutor(),
            ),
        )
    )

    assert run.failed
    assert len(run.steps) == 1
    assert run.steps[0].step_id == STEP_ID
    assert run.steps[0].status is WorkflowStepStatus.FAILED

    failure = run.steps[0].attempts[-1].failure

    assert failure is not None
    assert failure.exception_type == "RuntimeError"
    assert failure.message == "Step exploded."


def test_workflow_run_renders_real_step_failure_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_failing_runtime(
        monkeypatch,
        tmp_path,
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.TEXT,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == ""
    assert "Status: failed\n" in captured.out
    assert "Failed: 1\n" in captured.out
    assert f"ID: {STEP_ID}\n" in captured.out
    assert "Model exploded." in captured.out


def test_workflow_run_persists_real_step_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_failing_runtime(
        monkeypatch,
        tmp_path,
    )

    result = run_workflow(
        WORKFLOW_ID,
        output=WorkflowOutputFormat.TEXT,
    )

    captured = capsys.readouterr()

    runs = SQLiteWorkflowRunRepository(database).runs_for_workflow(WORKFLOW_ID)

    assert result == 1
    assert len(runs) == 1
    assert runs[0].failed
    assert runs[0].steps[0].status is WorkflowStepStatus.FAILED
    assert f"Run ID: {runs[0].id}\n" in captured.out
