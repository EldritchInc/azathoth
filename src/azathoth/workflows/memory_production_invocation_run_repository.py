"""In-memory persistence for production invocation run associations."""

from uuid import UUID

from azathoth.workflows.production_invocation_run import (
    ProductionInvocationRun,
)


class InMemoryProductionInvocationRunRepository:
    """Persist production invocation run associations in memory."""

    def __init__(
        self,
    ) -> None:
        """Initialize empty invocation run persistence."""

        self._associations: list[ProductionInvocationRun] = []
        self._by_invocation_id: dict[
            UUID,
            ProductionInvocationRun,
        ] = {}

    def save(
        self,
        association: ProductionInvocationRun,
    ) -> None:
        """Persist one immutable invocation run association."""

        if association.invocation_id in self._by_invocation_id:
            raise ValueError("Production invocation already has a workflow run.")

        self._associations.append(
            association,
        )

        self._by_invocation_id[association.invocation_id] = association

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationRun | None:
        """Return the run association for one production invocation."""

        return self._by_invocation_id.get(
            invocation_id,
        )

    def associations(
        self,
    ) -> tuple[ProductionInvocationRun, ...]:
        """Return invocation run associations in insertion order."""

        return tuple(
            self._associations,
        )
