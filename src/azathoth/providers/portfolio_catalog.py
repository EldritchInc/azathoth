"""Compose current model catalogs with organizational portfolio authorization."""

from azathoth.providers.catalog import ModelCatalog
from azathoth.providers.portfolio import ModelPortfolio


def model_catalog_for_portfolio(
    *,
    catalog: ModelCatalog,
    portfolio: ModelPortfolio,
) -> ModelCatalog:
    """Return currently available models authorized by the portfolio."""

    models = []

    for entry in portfolio.entries:
        model = catalog.get(entry.identifier)

        if model is not None:
            models.append(model)

    return ModelCatalog(models=tuple(models))
