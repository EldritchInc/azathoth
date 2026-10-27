"""End-to-end CLI tests promoting and invoking a workflow that reads its input.

`examples/workflows/classify-sentiment.json` renders its prompt from the
workflow input, as every realistic workflow does. These tests drive it through
the same commands an operator runs: import, authorize, promote, inspect and
invoke.
"""

import json
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    main,
)
from azathoth.prompting import (
    ContextPromptStrategySpec,
    FixedModelSelection,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.workflows import SQLiteWorkflowProductionStateRepository

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "classify-sentiment.json"

WORKFLOW_ID = UUID("5e2e0b6a-3c1d-4b7e-9f20-000000000001")

STEP_ID = UUID("5e2e0b6a-3c1d-4b7e-9f20-000000000002")

MODEL = FixedModelSelection(
    provider="test-provider",
    model="sentiment",
)


def configure_cli_runtime(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give the real CLI runtime one deterministic, current, executable model."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(
                ModelMetadata(
                    provider=MODEL.provider,
                    model=MODEL.model,
                    display_name=MODEL.identifier,
                ),
            )
        ),
    )

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                MODEL.identifier: DeterministicLanguageModel(
                    provider=MODEL.provider,
                    model=MODEL.model,
                    response_text="positive",
                ),
            }
        ),
    )


def run_cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> str:
    """Run one CLI command, require success, and return its standard output."""

    status = main(arguments)
    captured = capsys.readouterr()

    assert status == 0, captured.err

    return captured.out


def import_authorize_and_promote(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """Prepare the sentiment workflow and return the promotion output."""

    configure_cli_runtime(
        database=tmp_path / "azathoth.db",
        monkeypatch=monkeypatch,
    )

    run_cli(capsys, "workflow", "import", str(WORKFLOW_DOCUMENT))
    run_cli(capsys, "model", "authorize", MODEL.identifier)

    return run_cli(capsys, "workflow", "promote", str(WORKFLOW_ID))


def test_cli_promotes_a_context_prompt_workflow_onto_its_authorized_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = import_authorize_and_promote(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    state = SQLiteWorkflowProductionStateRepository(
        tmp_path / "azathoth.db",
    ).get(WORKFLOW_ID)

    assert state is not None

    step = state.specification.steps[0].specification

    assert isinstance(step, ContextPromptStrategySpec)
    assert step.model_selection == MODEL

    assert "Status: promoted\n" in output
    assert f"Prompt Step: {STEP_ID}\n" in output
    assert f"Primary Model: {MODEL.identifier}" in output


def test_cli_production_inspection_lists_context_prompt_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_authorize_and_promote(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    production = run_cli(capsys, "workflow", "production", str(WORKFLOW_ID))
    revisions = run_cli(capsys, "workflow", "revisions", str(WORKFLOW_ID))

    assert f"Prompt Step: {STEP_ID}\n" in production
    assert f"Primary Model: {MODEL.identifier}" in production
    assert MODEL.identifier in revisions
    assert "no prompt steps" not in revisions


def test_cli_invokes_a_promoted_context_prompt_workflow_with_its_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import_authorize_and_promote(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    output = run_cli(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input",
        '"The checkout flow was painless."',
        "--output",
        "result",
    )

    assert json.loads(output) == {"result": "positive"}
