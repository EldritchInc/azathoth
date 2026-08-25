"""Reconstruct model portfolios from durable repositories."""

from azathoth.providers.portfolio import (
    ModelPortfolio,
)
from azathoth.providers.portfolio_repository import (
    ModelPortfolioRepository,
)


class ModelPortfolioLoader:
    """Load immutable model portfolios from repository state."""

    def __init__(
        self,
        repository: ModelPortfolioRepository,
    ) -> None:
        self._repository = repository

    def load_portfolio(
        self,
    ) -> ModelPortfolio:
        """Reconstruct the organization's authorized model portfolio."""

        return ModelPortfolio(entries=self._repository.entries())
