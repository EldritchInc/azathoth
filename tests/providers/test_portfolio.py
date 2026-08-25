"""Tests for organizational model portfolio policy."""

import pytest
from pydantic import ValidationError

from azathoth.providers import (
    ModelPortfolio,
    ModelPortfolioEntry,
)


def create_entry(
    *,
    provider: str = "openrouter",
    model: str = "example/frontier",
) -> ModelPortfolioEntry:
    """Create one deterministic portfolio entry."""

    return ModelPortfolioEntry(
        provider=provider,
        model=model,
    )


def test_model_portfolio_entry_exposes_qualified_identifier() -> None:
    entry = create_entry()

    assert entry.identifier == "openrouter/example/frontier"


def test_model_portfolio_entry_preserves_provider_native_model_identifier() -> None:
    entry = create_entry(
        provider="openrouter",
        model="anthropic/claude-sonnet-latest",
    )

    assert entry.provider == "openrouter"

    assert entry.model == "anthropic/claude-sonnet-latest"

    assert entry.identifier == ("openrouter/anthropic/claude-sonnet-latest")


def test_model_portfolio_defaults_to_empty() -> None:
    portfolio = ModelPortfolio()

    assert portfolio.entries == ()
    assert portfolio.identifiers == ()


def test_model_portfolio_preserves_entry_order() -> None:
    first = create_entry(model="example/alpha")

    second = create_entry(model="example/beta")

    portfolio = ModelPortfolio(
        entries=(
            first,
            second,
        )
    )

    assert portfolio.entries == (
        first,
        second,
    )

    assert portfolio.identifiers == (
        "openrouter/example/alpha",
        "openrouter/example/beta",
    )


def test_model_portfolio_resolves_authorized_model() -> None:
    first = create_entry(model="example/alpha")

    second = create_entry(model="example/beta")

    portfolio = ModelPortfolio(
        entries=(
            first,
            second,
        )
    )

    assert portfolio.get("openrouter/example/beta") is second


def test_model_portfolio_returns_none_for_unauthorized_model() -> None:
    portfolio = ModelPortfolio(entries=(create_entry(),))

    assert portfolio.get("openrouter/example/missing") is None


def test_model_portfolio_allows_same_native_identifier_across_providers() -> None:
    first = create_entry(
        provider="provider-a",
        model="frontier",
    )

    second = create_entry(
        provider="provider-b",
        model="frontier",
    )

    portfolio = ModelPortfolio(
        entries=(
            first,
            second,
        )
    )

    assert portfolio.identifiers == (
        "provider-a/frontier",
        "provider-b/frontier",
    )


def test_model_portfolio_rejects_duplicate_identifiers() -> None:
    entry = create_entry()

    with pytest.raises(
        ValidationError,
        match=("Model portfolio cannot contain duplicate model identifiers"),
    ):
        ModelPortfolio(
            entries=(
                entry,
                entry,
            )
        )


def test_model_portfolio_entry_is_immutable() -> None:
    entry = create_entry()

    assert entry.model_config["frozen"]


def test_model_portfolio_is_immutable() -> None:
    portfolio = ModelPortfolio()

    assert portfolio.model_config["frozen"]
