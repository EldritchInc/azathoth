"""Tests for composing current catalogs with model portfolios."""

from azathoth.providers import (
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    model_catalog_for_portfolio,
)


def create_model(
    *,
    provider: str = "provider-a",
    model: str = "model-a",
) -> ModelMetadata:
    """Create deterministic current model metadata."""

    return ModelMetadata(
        provider=provider,
        model=model,
        display_name=model,
        context_window_tokens=128_000,
    )


def create_entry(
    *,
    provider: str = "provider-a",
    model: str = "model-a",
) -> ModelPortfolioEntry:
    """Create deterministic portfolio authorization."""

    return ModelPortfolioEntry(
        provider=provider,
        model=model,
    )


def test_empty_portfolio_produces_empty_catalog() -> None:
    catalog = ModelCatalog(
        models=(
            create_model(
                model="available",
            ),
        )
    )

    authorized = model_catalog_for_portfolio(
        catalog=catalog,
        portfolio=ModelPortfolio(),
    )

    assert authorized.models == ()


def test_portfolio_catalog_contains_only_current_authorized_models() -> None:
    authorized_model = create_model(
        model="authorized",
    )

    unauthorized_model = create_model(
        model="unauthorized",
    )

    catalog = ModelCatalog(
        models=(
            authorized_model,
            unauthorized_model,
        )
    )

    portfolio = ModelPortfolio(
        entries=(
            create_entry(
                model="authorized",
            ),
        )
    )

    authorized = model_catalog_for_portfolio(
        catalog=catalog,
        portfolio=portfolio,
    )

    assert authorized.models == (authorized_model,)


def test_portfolio_catalog_excludes_authorized_model_that_is_not_current() -> None:
    current_model = create_model(
        model="current",
    )

    catalog = ModelCatalog(models=(current_model,))

    portfolio = ModelPortfolio(
        entries=(
            create_entry(
                model="removed",
            ),
            create_entry(
                model="current",
            ),
        )
    )

    authorized = model_catalog_for_portfolio(
        catalog=catalog,
        portfolio=portfolio,
    )

    assert authorized.models == (current_model,)

    assert authorized.get("provider-a/removed") is None


def test_portfolio_catalog_preserves_portfolio_order() -> None:
    first = create_model(
        model="first",
    )

    second = create_model(
        model="second",
    )

    third = create_model(
        model="third",
    )

    catalog = ModelCatalog(
        models=(
            first,
            second,
            third,
        )
    )

    portfolio = ModelPortfolio(
        entries=(
            create_entry(
                model="third",
            ),
            create_entry(
                model="first",
            ),
        )
    )

    authorized = model_catalog_for_portfolio(
        catalog=catalog,
        portfolio=portfolio,
    )

    assert authorized.models == (
        third,
        first,
    )

    assert authorized.identifiers == (
        "provider-a/third",
        "provider-a/first",
    )


def test_portfolio_catalog_uses_provider_qualified_identity() -> None:
    first = create_model(
        provider="provider-a",
        model="shared",
    )

    second = create_model(
        provider="provider-b",
        model="shared",
    )

    catalog = ModelCatalog(
        models=(
            first,
            second,
        )
    )

    portfolio = ModelPortfolio(
        entries=(
            create_entry(
                provider="provider-b",
                model="shared",
            ),
        )
    )

    authorized = model_catalog_for_portfolio(
        catalog=catalog,
        portfolio=portfolio,
    )

    assert authorized.models == (second,)

    assert authorized.identifiers == ("provider-b/shared",)
