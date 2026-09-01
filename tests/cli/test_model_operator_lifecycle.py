"""End-to-end tests for the CLI model operator lifecycle."""

from pathlib import Path

import pytest

import azathoth.cli.models as model_commands
from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
    authorize_model,
    deauthorize_model,
    list_portfolio_models,
)
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.providers import (
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    SQLiteModelPortfolioRepository,
)

MODEL_IDENTIFIER = "openrouter/example/operator-model"
MODEL = "example/operator-model"


def create_current_model() -> ModelMetadata:
    """Create deterministic current provider model metadata."""

    return ModelMetadata(
        provider="openrouter",
        model=MODEL,
        display_name="Operator Model",
        context_window_tokens=128_000,
        maximum_output_tokens=16_384,
    )


def configure_environment(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure deterministic CLI persistence."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )

    monkeypatch.setenv(
        OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
        "test-openrouter-key",
    )


def load_portfolio(
    database: Path,
) -> ModelPortfolio:
    """Load the durable organizational model portfolio."""

    repository = SQLiteModelPortfolioRepository(database)

    return ModelPortfolio(
        entries=repository.entries(),
    )


def configure_runtime_state(
    *,
    monkeypatch: pytest.MonkeyPatch,
    database: Path,
    models: ModelCatalog,
) -> None:
    """Reconstruct CLI-visible runtime state from durable authorization."""

    def fake_load_runtime(
        configuration: CliRuntimeConfiguration,
    ) -> object:
        assert configuration.database == database

        return type(
            "Runtime",
            (),
            {
                "models": models,
                "portfolio": load_portfolio(database),
            },
        )()

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        fake_load_runtime,
    )


def test_model_operator_lifecycle_persists_authorization_across_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    model = create_current_model()

    configure_environment(
        database=database,
        monkeypatch=monkeypatch,
    )

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
    )

    assert authorize_model(MODEL_IDENTIFIER) == 0

    captured = capsys.readouterr()

    assert captured.out == (f"Authorized model {MODEL_IDENTIFIER}.\n")
    assert captured.err == ""

    persisted = SQLiteModelPortfolioRepository(database)

    assert tuple(entry.identifier for entry in persisted.entries()) == (MODEL_IDENTIFIER,)

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
    )

    assert list_portfolio_models() == 0

    captured = capsys.readouterr()

    assert captured.out == f"{MODEL_IDENTIFIER}\n"
    assert captured.err == ""

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
    )

    assert deauthorize_model(MODEL_IDENTIFIER) == 0

    captured = capsys.readouterr()

    assert captured.out == (f"Deauthorized model {MODEL_IDENTIFIER}.\n")
    assert captured.err == ""

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
    )

    assert list_portfolio_models() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""

    assert persisted.entries() == ()


def test_model_operator_lifecycle_cannot_reauthorize_unavailable_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    model = create_current_model()

    configure_environment(
        database=database,
        monkeypatch=monkeypatch,
    )

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
    )

    assert authorize_model(MODEL_IDENTIFIER) == 0

    capsys.readouterr()

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
    )

    assert deauthorize_model(MODEL_IDENTIFIER) == 0

    capsys.readouterr()

    configure_runtime_state(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
    )

    assert authorize_model(MODEL_IDENTIFIER) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (f"Model {MODEL_IDENTIFIER!r} is not currently available.\n")

    repository = SQLiteModelPortfolioRepository(database)

    assert repository.entries() == ()
