"""Persistence contracts for production workflow invocations."""

from typing import Protocol
from uuid import UUID

from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationResult,
)


class IdempotencyKeyInUseError(ValueError):
    """Raised when an invocation is saved under a key another one holds.

    Nothing is saved. The key is unique across recorded invocations, so of
    two requests racing with one key, exactly one is saved (ADR 0097).
    """

    def __init__(
        self,
        key: str,
    ) -> None:
        super().__init__(f"Idempotency key {key!r} is already recorded on a production invocation.")

        self.key = key


class ProductionInvocationRepository(Protocol):
    """Persist production invocations and their terminal results."""

    def save(
        self,
        invocation: ProductionInvocation,
    ) -> None:
        """Persist one production invocation without replacing history.

        Raises:
            IdempotencyKeyInUseError: The invocation's idempotency key is
                already recorded on another invocation.
            ValueError: The invocation is already recorded.
        """

        ...

    def get(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocation | None:
        """Return one production invocation by identifier."""

        ...

    def invocation_for_idempotency_key(
        self,
        key: str,
    ) -> ProductionInvocation | None:
        """Return the production invocation recorded under one idempotency key."""

        ...

    def invocations(
        self,
    ) -> tuple[ProductionInvocation, ...]:
        """Return all production invocations in insertion order."""

        ...

    def invocations_for_workflow(
        self,
        workflow_id: UUID,
    ) -> tuple[ProductionInvocation, ...]:
        """Return production invocations for one workflow in insertion order."""

        ...

    def save_result(
        self,
        result: ProductionInvocationResult,
    ) -> None:
        """Persist the single terminal result for one invocation."""

        ...

    def result(
        self,
        invocation_id: UUID,
    ) -> ProductionInvocationResult | None:
        """Return the terminal result for one invocation, if recorded."""

        ...
