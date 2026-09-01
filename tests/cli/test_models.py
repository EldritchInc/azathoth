"""Tests for current provider model CLI commands."""

from types import SimpleNamespace

import pytest

import azathoth.cli.models as model_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    list_models,
    show_model,
)
from azathoth.providers import (
    ModelCapability,
    ModelCatalog,
    ModelMetadata,
    ModelModality,
    ModelPricing,
)

FIRST_IDENTIFIER = "provider-a/example/alpha"
SECOND_IDENTIFIER = "provider-b/example/beta"
UNKNOWN_IDENTIFIER = "provider-a/example/missing"


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

    def load_test_runtime(
        configuration: CliRuntimeConfiguration,
    ) -> SimpleNamespace:
        assert isinstance(
            configuration,
            CliRuntimeConfiguration,
        )

        return SimpleNamespace(
            models=catalog,
        )

    monkeypatch.setattr(
        model_commands,
        "load_runtime",
        load_test_runtime,
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
    second = create_second_model()
    first = create_first_model()

    configure_models(
        monkeypatch,
        ModelCatalog(
            models=(
                second,
                first,
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
