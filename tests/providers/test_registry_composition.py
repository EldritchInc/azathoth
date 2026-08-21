"""Tests for deterministic language model registry composition."""

import pytest

from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
)

FIRST_IDENTIFIER = "first-provider/first-model"
SECOND_IDENTIFIER = "second-provider/second-model"
THIRD_IDENTIFIER = "third-provider/third-model"


def create_model(
    *,
    provider: str,
    model: str,
) -> DeterministicLanguageModel:
    """Create one deterministic executable language model."""

    return DeterministicLanguageModel(
        provider=provider,
        model=model,
    )


def test_registry_compose_combines_multiple_registries() -> None:
    first_model = create_model(
        provider="first-provider",
        model="first-model",
    )

    second_model = create_model(
        provider="second-provider",
        model="second-model",
    )

    first_registry = LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: first_model,
        },
    )

    second_registry = LanguageModelRegistry(
        models={
            SECOND_IDENTIFIER: second_model,
        },
    )

    combined = LanguageModelRegistry.compose(
        (
            first_registry,
            second_registry,
        )
    )

    assert combined.get(FIRST_IDENTIFIER) is first_model

    assert combined.get(SECOND_IDENTIFIER) is second_model


def test_registry_compose_preserves_registry_and_model_order() -> None:
    first_registry = LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: create_model(
                provider="first-provider",
                model="first-model",
            ),
            SECOND_IDENTIFIER: create_model(
                provider="second-provider",
                model="second-model",
            ),
        },
    )

    second_registry = LanguageModelRegistry(
        models={
            THIRD_IDENTIFIER: create_model(
                provider="third-provider",
                model="third-model",
            ),
        },
    )

    combined = LanguageModelRegistry.compose(
        (
            first_registry,
            second_registry,
        )
    )

    assert combined.identifiers == (
        FIRST_IDENTIFIER,
        SECOND_IDENTIFIER,
        THIRD_IDENTIFIER,
    )


def test_registry_compose_rejects_duplicate_identifiers() -> None:
    first_registry = LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: create_model(
                provider="first-provider",
                model="first-model",
            ),
        },
    )

    duplicate_registry = LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: create_model(
                provider="first-provider",
                model="first-model",
            ),
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            "Language model identifier 'first-provider/first-model' is registered more than once"
        ),
    ):
        LanguageModelRegistry.compose(
            (
                first_registry,
                duplicate_registry,
            )
        )


def test_registry_compose_accepts_empty_registry_collection() -> None:
    combined = LanguageModelRegistry.compose(())

    assert combined.identifiers == ()


def test_registry_compose_does_not_modify_source_registries() -> None:
    first_model = create_model(
        provider="first-provider",
        model="first-model",
    )

    second_model = create_model(
        provider="second-provider",
        model="second-model",
    )

    first_registry = LanguageModelRegistry(
        models={
            FIRST_IDENTIFIER: first_model,
        },
    )

    second_registry = LanguageModelRegistry(
        models={
            SECOND_IDENTIFIER: second_model,
        },
    )

    combined = LanguageModelRegistry.compose(
        (
            first_registry,
            second_registry,
        )
    )

    assert first_registry.identifiers == (FIRST_IDENTIFIER,)

    assert second_registry.identifiers == (SECOND_IDENTIFIER,)

    assert combined.identifiers == (
        FIRST_IDENTIFIER,
        SECOND_IDENTIFIER,
    )
