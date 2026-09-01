"""Tests for model commands in the Azathoth CLI."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import azathoth.cli.models as model_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    authorize_model,
    deauthorize_model,
    list_models,
    list_portfolio_models,
    show_model,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelModality,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelPricing,
    SQLiteModelPortfolioRepository,
)

FIRST_IDENTIFIER = "provider-a/example/alpha"
SECOND_IDENTIFIER = "provider-b/example/beta"
UNKNOWN_IDENTIFIER = "provider-a/example/missing"

AUTHORIZED_FIRST_IDENTIFIER = "openrouter/example/authorized-alpha"
AUTHORIZED_SECOND_IDENTIFIER = "openrouter/example/authorized-beta"


def create_first_model() -> ModelMetadata:
    """Create deterministic current provider metadata."""

    return ModelMetadata(
        provider="provider-a",
        model="example/alpha",
        display_name="Alpha",
        input_modalities=frozenset(
            {
                ModelModality.TEXT,
                ModelModality.IMAGE,
            }
        ),
        output_modalities=frozenset(
            {
                ModelModality.TEXT,
            }
        ),
        capabilities=frozenset(
            {
                ModelCapability.VISION,
                ModelCapability.STRUCTURED_OUTPUT,
            }
        ),
        context_window_tokens=128_000,
        maximum_output_tokens=16_384,
        pricing=ModelPricing(
            input_usd_per_million_tokens=1.25,
            output_usd_per_million_tokens=5.0,
        ),
    )


def create_second_model() -> ModelMetadata:
    """Create model with unknown optional provider metadata."""

    return ModelMetadata(
        provider="provider-b",
        model="example/beta",
        display_name="Beta",
        context_window_tokens=None,
        maximum_output_tokens=None,
        pricing=None,
    )


def configure_models(
    monkeypatch: pytest.MonkeyPatch,
    catalog: ModelCatalog,
) -> None:
    """Configure deterministic current runtime model state."""

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: object(),
    )

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        lambda _configuration: SimpleNamespace(
            models=catalog,
        ),
    )


def configure_portfolio(
    monkeypatch: pytest.MonkeyPatch,
    portfolio: ModelPortfolio,
) -> None:
    """Configure deterministic organizational model authorization."""

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: object(),
    )

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        lambda _configuration: SimpleNamespace(
            portfolio=portfolio,
        ),
    )


def configure_authorization_runtime(
    *,
    monkeypatch: pytest.MonkeyPatch,
    database: Path,
    models: ModelCatalog,
    portfolio: ModelPortfolio,
) -> None:
    """Configure deterministic model authorization state."""

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
            models=models,
            portfolio=portfolio,
        ),
    )


def test_model_list_prints_current_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog = ModelCatalog(
        models=(
            create_first_model(),
            create_second_model(),
        )
    )

    configure_models(
        monkeypatch,
        catalog,
    )

    result = list_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (f"{FIRST_IDENTIFIER}  Alpha\n{SECOND_IDENTIFIER}  Beta\n")
    assert captured.err == ""


def test_model_list_preserves_current_catalog_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_models(
        monkeypatch,
        ModelCatalog(
            models=(
                create_second_model(),
                create_first_model(),
            )
        ),
    )

    result = list_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (f"{SECOND_IDENTIFIER}  Beta\n{FIRST_IDENTIFIER}  Alpha\n")


def test_model_list_prints_nothing_for_empty_current_catalog(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_models(
        monkeypatch,
        ModelCatalog(),
    )

    result = list_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_model_show_prints_current_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = create_first_model()

    configure_models(
        monkeypatch,
        ModelCatalog(
            models=(model,),
        ),
    )

    result = show_model(model.identifier)

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (
        f"ID: {FIRST_IDENTIFIER}\n"
        "Provider: provider-a\n"
        "Model: example/alpha\n"
        "Name: Alpha\n"
        "Input Modalities: image, text\n"
        "Output Modalities: text\n"
        "Capabilities: structured_output, vision\n"
        "Context Window: 128000\n"
        "Maximum Output Tokens: 16384\n"
        "Input Price: $1.250000 per million tokens\n"
        "Output Price: $5.000000 per million tokens\n"
    )
    assert captured.err == ""


def test_model_show_renders_unknown_optional_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = create_second_model()

    configure_models(
        monkeypatch,
        ModelCatalog(
            models=(model,),
        ),
    )

    result = show_model(model.identifier)

    captured = capsys.readouterr()

    assert result == 0
    assert "Capabilities: none\n" in captured.out
    assert "Context Window: unknown\n" in captured.out
    assert "Maximum Output Tokens: unknown\n" in captured.out
    assert "Input Price: unknown\n" in captured.out
    assert "Output Price: unknown\n" in captured.out


def test_model_show_reports_model_not_currently_available(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_models(
        monkeypatch,
        ModelCatalog(),
    )

    result = show_model(UNKNOWN_IDENTIFIER)

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Model {UNKNOWN_IDENTIFIER!r} is not currently available.\n")


def test_model_portfolio_prints_authorized_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    portfolio = ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider="openrouter",
                model="example/authorized-alpha",
            ),
            ModelPortfolioEntry(
                provider="openrouter",
                model="example/authorized-beta",
            ),
        )
    )

    configure_portfolio(
        monkeypatch,
        portfolio,
    )

    result = list_portfolio_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (f"{AUTHORIZED_FIRST_IDENTIFIER}\n{AUTHORIZED_SECOND_IDENTIFIER}\n")
    assert captured.err == ""


def test_model_portfolio_preserves_authorization_order(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    portfolio = ModelPortfolio(
        entries=(
            ModelPortfolioEntry(
                provider="openrouter",
                model="example/authorized-beta",
            ),
            ModelPortfolioEntry(
                provider="openrouter",
                model="example/authorized-alpha",
            ),
        )
    )

    configure_portfolio(
        monkeypatch,
        portfolio,
    )

    result = list_portfolio_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == (f"{AUTHORIZED_SECOND_IDENTIFIER}\n{AUTHORIZED_FIRST_IDENTIFIER}\n")


def test_model_portfolio_prints_nothing_when_no_models_are_authorized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_portfolio(
        monkeypatch,
        ModelPortfolio(),
    )

    result = list_portfolio_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert captured.err == ""


def test_model_portfolio_does_not_require_current_model_catalog(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    entry = ModelPortfolioEntry(
        provider="openrouter",
        model="example/unavailable",
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: object(),
    )

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        lambda _configuration: SimpleNamespace(
            portfolio=ModelPortfolio(
                entries=(entry,),
            ),
            models=ModelCatalog(),
        ),
    )

    result = list_portfolio_models()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == f"{entry.identifier}\n"
    assert captured.err == ""


def test_model_authorize_persists_current_provider_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    model = create_first_model()

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
        portfolio=ModelPortfolio(),
    )

    result = authorize_model(model.identifier)

    captured = capsys.readouterr()

    repository = SQLiteModelPortfolioRepository(database)

    assert result == 0
    assert repository.entries() == (
        ModelPortfolioEntry(
            provider=model.provider,
            model=model.model,
        ),
    )
    assert captured.out == (f"Authorized model {model.identifier}.\n")
    assert captured.err == ""


def test_model_authorize_rejects_model_not_currently_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
        portfolio=ModelPortfolio(),
    )

    result = authorize_model(UNKNOWN_IDENTIFIER)

    captured = capsys.readouterr()

    repository = SQLiteModelPortfolioRepository(database)

    assert result == 1
    assert repository.entries() == ()
    assert captured.out == ""
    assert captured.err == (f"Model {UNKNOWN_IDENTIFIER!r} is not currently available.\n")


def test_model_authorize_rejects_already_authorized_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    model = create_first_model()

    entry = ModelPortfolioEntry(
        provider=model.provider,
        model=model.model,
    )

    repository = SQLiteModelPortfolioRepository(database)
    repository.save(entry)

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
        portfolio=ModelPortfolio(
            entries=(entry,),
        ),
    )

    result = authorize_model(model.identifier)

    captured = capsys.readouterr()

    assert result == 1
    assert repository.entries() == (entry,)
    assert captured.out == ""
    assert captured.err == (f"Model {model.identifier!r} is already authorized.\n")


def test_model_authorize_uses_provider_reported_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"
    model = create_first_model()

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(
            models=(model,),
        ),
        portfolio=ModelPortfolio(),
    )

    assert authorize_model(model.identifier) == 0

    repository = SQLiteModelPortfolioRepository(database)

    entry = repository.get(model.identifier)

    assert entry is not None
    assert entry.provider == model.provider
    assert entry.model == model.model
    assert entry.identifier == model.identifier


def test_model_deauthorize_deletes_authorized_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    entry = ModelPortfolioEntry(
        provider="provider-a",
        model="example/alpha",
    )

    repository = SQLiteModelPortfolioRepository(database)
    repository.save(entry)

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
        portfolio=ModelPortfolio(
            entries=(entry,),
        ),
    )

    result = deauthorize_model(entry.identifier)

    captured = capsys.readouterr()

    assert result == 0
    assert repository.entries() == ()
    assert captured.out == (f"Deauthorized model {entry.identifier}.\n")

    assert captured.err == ""


def test_model_deauthorize_rejects_model_not_authorized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
        portfolio=ModelPortfolio(),
    )

    result = deauthorize_model(UNKNOWN_IDENTIFIER)

    captured = capsys.readouterr()

    repository = SQLiteModelPortfolioRepository(database)

    assert result == 1
    assert repository.entries() == ()
    assert captured.out == ""
    assert captured.err == (f"Model {UNKNOWN_IDENTIFIER!r} is not authorized.\n")


def test_model_deauthorize_does_not_require_current_provider_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    entry = ModelPortfolioEntry(
        provider="openrouter",
        model="example/removed-by-provider",
    )

    repository = SQLiteModelPortfolioRepository(database)
    repository.save(entry)

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
        portfolio=ModelPortfolio(
            entries=(entry,),
        ),
    )

    result = deauthorize_model(entry.identifier)

    captured = capsys.readouterr()

    assert result == 0
    assert repository.entries() == ()
    assert captured.out == (f"Deauthorized model {entry.identifier}.\n")
    assert captured.err == ""


def test_model_deauthorize_preserves_other_authorized_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "azathoth.db"

    first = ModelPortfolioEntry(
        provider="provider-a",
        model="example/alpha",
    )

    second = ModelPortfolioEntry(
        provider="provider-b",
        model="example/beta",
    )

    repository = SQLiteModelPortfolioRepository(database)
    repository.save(first)
    repository.save(second)

    configure_authorization_runtime(
        monkeypatch=monkeypatch,
        database=database,
        models=ModelCatalog(),
        portfolio=ModelPortfolio(
            entries=(
                first,
                second,
            ),
        ),
    )

    assert deauthorize_model(first.identifier) == 0

    assert repository.entries() == (second,)
