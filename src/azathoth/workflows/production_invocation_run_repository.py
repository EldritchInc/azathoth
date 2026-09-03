"""Persistence contract for production invocation run associations."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)


class ProductionInvocationRunRepository(Protocol):
    """Persist production invocation run associations."""

    def save(
        self,
        association: ProductionInvocationRun,
    ) -> None:
        """Persist one immutable invocation run association."""

        ...

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationRun | None:
        """Return the run association for one production invocation."""

        ...

    def associations(
        self,
    ) -> tuple[ProductionInvocationRun, ...]:
        """Return invocation run associations in insertion order."""

        ...
