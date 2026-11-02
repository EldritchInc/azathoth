"""The index of the runs each step of another run started (ADR 0105).

A child records its lineage in its own initial context (ADR 0104), so it
always knows its parent. The index lets the parent find its children: a run
started with lineage records one `RunChild` when it starts, under its
parent's run, before it journals anything else. A run is a child once, so a
resumed child is not recorded again.
"""

import threading
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from azathoth.context import WorkflowLineage


class RunChild(BaseModel):
    """One run a step of another run started."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    child_run_id: UUID
    child_workflow_id: UUID
    child_invocation_id: UUID | None = None
    parent_run_id: UUID
    parent_step_id: UUID
    parent_attempt: int = Field(ge=1)
    root_run_id: UUID
    depth: int = Field(ge=1)
    recorded_at: datetime

    @classmethod
    def of(
        cls,
        lineage: WorkflowLineage,
        *,
        run_id: UUID,
        workflow_id: UUID,
        invocation_id: UUID | None,
        recorded_at: datetime,
    ) -> "RunChild":
        """Return the index entry of a run started with this lineage."""

        return cls(
            child_run_id=run_id,
            child_workflow_id=workflow_id,
            child_invocation_id=invocation_id,
            parent_run_id=lineage.parent.run_id,
            parent_step_id=lineage.parent.step_id,
            parent_attempt=lineage.parent.attempt,
            root_run_id=lineage.root.run_id,
            depth=lineage.depth,
            recorded_at=recorded_at,
        )


class RunChildRepository(Protocol):
    """Persist the index of children, one entry per child run."""

    def record(
        self,
        child: RunChild,
    ) -> None:
        """Record one child; a child already recorded is left as it is."""

        ...

    def children_of(
        self,
        parent_run_id: UUID,
    ) -> tuple[RunChild, ...]:
        """Return a run's children, in the order they started."""

        ...


class InMemoryRunChildRepository:
    """Keep the index of children in memory, for tests and short-lived processes."""

    def __init__(
        self,
    ) -> None:
        self._children: dict[UUID, RunChild] = {}
        self._lock = threading.Lock()

    def record(
        self,
        child: RunChild,
    ) -> None:
        """Record one child; a child already recorded is left as it is."""

        with self._lock:
            self._children.setdefault(child.child_run_id, child)

    def children_of(
        self,
        parent_run_id: UUID,
    ) -> tuple[RunChild, ...]:
        """Return a run's children, in the order they started."""

        with self._lock:
            return tuple(
                child for child in self._children.values() if child.parent_run_id == parent_run_id
            )


__all__ = [
    "InMemoryRunChildRepository",
    "RunChild",
    "RunChildRepository",
]
