"""Tests for unknown provider model context limits."""

from azathoth.providers import (
    ModelMetadata,
    ModelQuery,
)


def create_model(
    *,
    context_window_tokens: int | None = None,
) -> ModelMetadata:
    """Create deterministic model metadata with an optional context limit."""

    return ModelMetadata(
        provider="example",
        model="example-model",
        display_name="Example Model",
        context_window_tokens=context_window_tokens,
    )


def test_model_metadata_allows_unknown_context_window() -> None:
    model = create_model()

    assert model.context_window_tokens is None


def test_unknown_context_window_matches_when_no_minimum_is_required() -> None:
    model = create_model()

    query = ModelQuery()

    assert query.matches(model)


def test_unknown_context_window_does_not_satisfy_minimum_requirement() -> None:
    model = create_model()

    query = ModelQuery(
        minimum_context_window_tokens=128_000,
    )

    assert not query.matches(model)


def test_known_context_window_satisfies_supported_minimum() -> None:
    model = create_model(
        context_window_tokens=128_000,
    )

    query = ModelQuery(
        minimum_context_window_tokens=64_000,
    )

    assert query.matches(model)
