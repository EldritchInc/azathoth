"""Tests for guarding model deauthorization against production usage."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import azathoth.cli.application as application
import azathoth.cli.models as model_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    build_parser,
    deauthorize_model,
    main,
)
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    ModelPortfolio,
    ModelPortfolioEntry,
    Prompt,
    SQLiteModelPortfolioRepository,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRepository,
    WorkflowMetadata,
    WorkflowProductionModelSubstitution,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

STEP_ID = UUID("44444444-4444-4444-4444-444444444444")

STRATEGY_ID = UUID("77777777-7777-7777-7777-777777777777")

ENTRY = ModelPortfolioEntry(
    provider="openrouter",
    model="example-model",
)

PRIMARY_IDENTIFIER = "openrouter/primary-model"


def configure_runtime(
    *,
    monkeypatch: pytest.MonkeyPatch,
    database: Path,
) -> SQLiteModelPortfolioRepository:
    """Authorize the guarded model and point the CLI at an isolated database."""

    repository = SQLiteModelPortfolioRepository(database)
    repository.save(ENTRY)

    configuration = CliRuntimeConfiguration(
        database=database,
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        lambda _configuration: SimpleNamespace(
            portfolio=ModelPortfolio(
                entries=(ENTRY,),
            ),
        ),
    )

    return repository


def create_workflow(
    model_identifier: str,
) -> WorkflowSpecification:
    """Create a one-step workflow pinned to one exact model."""

    provider, model = model_identifier.split(
        "/",
        maxsplit=1,
    )

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="summarize",
            description="Summarize documents.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Summarize prompt",
                        description="Summarize prompt description.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Return exactly OK.",
                    ),
                    model_selection=FixedModelSelection(
                        provider=provider,
                        model=model,
                    ),
                ),
            ),
        ),
    )


def test_deauthorize_refuses_production_primary_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    repository = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    SQLiteWorkflowProductionStateRepository(database).set(
        WorkflowProductionState(
            specification=create_workflow(ENTRY.identifier),
        )
    )

    result = deauthorize_model(ENTRY.identifier)

    captured = capsys.readouterr()

    assert result == 1
    assert repository.entries() == (ENTRY,)
    assert captured.out == ""
    assert captured.err == "\n".join(
        (
            f"Model {ENTRY.identifier!r} is used by active production and was not deauthorized.",
            f"  summarize ({WORKFLOW_ID}): primary step {STEP_ID}",
            "Use --force to deauthorize anyway.",
            "",
        )
    )


def test_deauthorize_refuses_production_substitute_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    repository = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    SQLiteWorkflowProductionStateRepository(database).set(
        WorkflowProductionState(
            specification=create_workflow(PRIMARY_IDENTIFIER),
            model_substitutions=(
                WorkflowProductionModelSubstitution(
                    step_id=STEP_ID,
                    substitutes=(
                        FixedModelSelection(
                            provider=ENTRY.provider,
                            model=ENTRY.model,
                        ),
                    ),
                ),
            ),
        )
    )

    result = deauthorize_model(ENTRY.identifier)

    captured = capsys.readouterr()

    assert result == 1
    assert repository.entries() == (ENTRY,)
    assert f"  summarize ({WORKFLOW_ID}): substitute step {STEP_ID}" in captured.err


def test_forced_deauthorize_removes_production_model_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    repository = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    SQLiteWorkflowProductionStateRepository(database).set(
        WorkflowProductionState(
            specification=create_workflow(ENTRY.identifier),
        )
    )

    result = deauthorize_model(
        ENTRY.identifier,
        force=True,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert repository.entries() == ()
    assert captured.out == f"Deauthorized model {ENTRY.identifier}.\n"
    assert captured.err == "\n".join(
        (
            f"Warning: deauthorizing model {ENTRY.identifier!r} used by active production.",
            f"  summarize ({WORKFLOW_ID}): primary step {STEP_ID}",
            "",
        )
    )


def test_deauthorize_ignores_configured_workflows_outside_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    repository = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    SQLiteWorkflowRepository(database).save(create_workflow(ENTRY.identifier))

    result = deauthorize_model(ENTRY.identifier)

    captured = capsys.readouterr()

    assert result == 0
    assert repository.entries() == ()
    assert captured.out == f"Deauthorized model {ENTRY.identifier}.\n"
    assert captured.err == ""


def test_deauthorize_parser_defaults_force_to_false() -> None:
    arguments = build_parser().parse_args(
        (
            "model",
            "deauthorize",
            ENTRY.identifier,
        )
    )

    assert arguments.model_force is False


def test_deauthorize_parser_records_force() -> None:
    arguments = build_parser().parse_args(
        (
            "model",
            "deauthorize",
            ENTRY.identifier,
            "--force",
        )
    )

    assert arguments.model_force is True


def test_cli_dispatches_forced_deauthorize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_deauthorize_model(
        identifier: str,
        *,
        force: bool,
    ) -> int:
        calls.append(
            (
                identifier,
                force,
            )
        )

        return 41

    monkeypatch.setattr(
        application,
        "deauthorize_model",
        fake_deauthorize_model,
    )

    result = main(
        (
            "model",
            "deauthorize",
            ENTRY.identifier,
            "--force",
        )
    )

    assert result == 41
    assert calls == [
        (
            ENTRY.identifier,
            True,
        ),
    ]
