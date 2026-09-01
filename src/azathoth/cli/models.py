"""Current provider model commands for the Azathoth command-line application."""

import sys

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.providers import (
    ModelCapability,
    ModelMetadata,
    ModelModality,
)


def list_models() -> int:
    """List models currently available from configured providers."""

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    for model in runtime.models.models:
        print(f"{model.identifier}  {model.display_name}")

    return 0


def show_model(
    identifier: str,
) -> int:
    """Show one currently available provider model."""

    configuration = CliRuntimeConfiguration.from_environment()
    runtime = load_runtime(configuration)

    model = runtime.models.get(identifier)

    if model is None:
        print(
            f"Model {identifier!r} is not currently available.",
            file=sys.stderr,
        )

        return 1

    _print_model(model)

    return 0


def _print_model(
    model: ModelMetadata,
) -> None:
    """Render one current model using provider-neutral metadata."""

    print(f"ID: {model.identifier}")
    print(f"Provider: {model.provider}")
    print(f"Model: {model.model}")
    print(f"Name: {model.display_name}")

    print(f"Input Modalities: {_render_values(model.input_modalities)}")

    print(f"Output Modalities: {_render_values(model.output_modalities)}")

    print(f"Capabilities: {_render_values(model.capabilities)}")

    print(f"Context Window: {_render_optional_integer(model.context_window_tokens)}")

    print(f"Maximum Output Tokens: {_render_optional_integer(model.maximum_output_tokens)}")

    if model.pricing is None:
        print("Input Price: unknown")
        print("Output Price: unknown")
        return

    print(f"Input Price: ${model.pricing.input_usd_per_million_tokens:.6f} per million tokens")

    print(f"Output Price: ${model.pricing.output_usd_per_million_tokens:.6f} per million tokens")


def _render_values(
    values: frozenset[ModelCapability] | frozenset[ModelModality],
) -> str:
    """Render deterministic model enum values."""

    if not values:
        return "none"

    return ", ".join(sorted(value.value for value in values))


def _render_optional_integer(
    value: int | None,
) -> str:
    """Render an optional integer model property."""

    if value is None:
        return "unknown"

    return str(value)
