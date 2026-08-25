"""Tests for provider-neutral model discovery contracts."""

import asyncio

from azathoth.providers import (
    ProviderModel,
    ProviderModelDirectory,
)


class ExampleProviderModelDirectory:
    """Deterministic provider model directory for protocol tests."""

    def __init__(
        self,
        models: tuple[ProviderModel, ...],
    ) -> None:
        self._models = models

    @property
    def provider(
        self,
    ) -> str:
        """Return the deterministic provider identifier."""

        return "example"

    async def models(
        self,
    ) -> tuple[ProviderModel, ...]:
        """Return all deterministic provider models."""

        return self._models

    async def model(
        self,
        identifier: str,
    ) -> ProviderModel | None:
        """Return one deterministic provider model."""

        return next(
            (model for model in self._models if model.model == identifier),
            None,
        )


def create_provider_models() -> tuple[
    ProviderModel,
    ...,
]:
    """Create deterministic provider model state."""

    return (
        ProviderModel(
            provider="example",
            model="alpha",
            display_name="Alpha",
            context_window_tokens=8_192,
        ),
        ProviderModel(
            provider="example",
            model="beta",
            display_name="Beta",
            context_window_tokens=16_384,
        ),
    )


def require_provider_model_directory(
    directory: ProviderModelDirectory,
) -> ProviderModelDirectory:
    """Return a directory after static protocol validation."""

    return directory


def test_provider_model_directory_satisfies_protocol() -> None:
    directory = ExampleProviderModelDirectory(create_provider_models())

    resolved = require_provider_model_directory(directory)

    assert resolved is directory


def test_provider_model_directory_exposes_provider() -> None:
    directory: ProviderModelDirectory = ExampleProviderModelDirectory(create_provider_models())

    assert directory.provider == "example"


def test_provider_model_directory_lists_current_models() -> None:
    expected = create_provider_models()

    directory: ProviderModelDirectory = ExampleProviderModelDirectory(expected)

    models = asyncio.run(directory.models())

    assert models == expected


def test_provider_model_directory_resolves_current_model() -> None:
    directory: ProviderModelDirectory = ExampleProviderModelDirectory(create_provider_models())

    model = asyncio.run(directory.model("beta"))

    assert model is not None
    assert model.model == "beta"
    assert model.identifier == "example/beta"


def test_provider_model_directory_returns_none_for_unknown_model() -> None:
    directory: ProviderModelDirectory = ExampleProviderModelDirectory(create_provider_models())

    model = asyncio.run(directory.model("does-not-exist"))

    assert model is None
