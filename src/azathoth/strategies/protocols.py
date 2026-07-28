"""Protocols implemented by executable Azathoth strategies."""

from typing import Protocol

from azathoth.context import Context
from azathoth.strategies.models import StrategyMetadata, StrategyOutcome


class Strategy(Protocol):
    """An executable operation that can act on structured context."""

    @property
    def metadata(self) -> StrategyMetadata:
        """Return stable identifying metadata for this strategy."""

        ...

    async def run(self, context: Context) -> StrategyOutcome:
        """Execute the strategy against the supplied context."""

        ...
