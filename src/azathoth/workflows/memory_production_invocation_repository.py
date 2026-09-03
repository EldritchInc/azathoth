"""Deterministic in-memory persistence for production workflow invocations."""

from uuid import UUID

from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationResult,
)
from azathoth.workflows.production_invocation_repository import (
    ProductionInvocationRepository,
)


class InMemoryProductionInvocationRepository:
    """Store production invocations and terminal results in memory."""

    def __init__(
        self,
    ) -> None:
        self._invocations: dict[UUID, ProductionInvocation] = {}
        self._results: dict[UUID, ProductionInvocationResult] = {}

    def save(
        self,
        invocation: ProductionInvocation,
    ) -> None:
        """Persist one production invocation without replacing history."""

        if invocation.id in self._invocations:
            raise ValueError(f"Production invocation {invocation.id} already exists.")

        self._invocations[invocation.id] = invocation

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocation | None:
        """Return one production invocation by identifier."""

        return self._invocations.get(invocation_id)

    def invocations(
        self,
    ) -> tuple[ProductionInvocation, ...]:
        """Return all production invocations in insertion order."""

        return tuple(self._invocations.values())

    def invocations_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[ProductionInvocation, ...]:
        """Return production invocations for one workflow in insertion order."""

        return tuple(
            invocation
            for invocation in self._invocations.values()
            if invocation.workflow_id == workflow_id
        )

    def save_result(
        self,
        result: ProductionInvocationResult,
    ) -> None:
        """Persist the single terminal result for one invocation."""

        if result.invocation_id not in self._invocations:
            raise ValueError(f"Production invocation {result.invocation_id} does not exist.")

        if result.invocation_id in self._results:
            raise ValueError(
                f"Production invocation {result.invocation_id} already has a terminal result."
            )

        self._results[result.invocation_id] = result

    def result(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationResult | None:
        """Return the terminal result for one invocation, if recorded."""

        return self._results.get(invocation_id)


def require_production_invocation_repository(
    repository: ProductionInvocationRepository,
) -> ProductionInvocationRepository:
    """Return a repository after static protocol validation."""

    return repository
