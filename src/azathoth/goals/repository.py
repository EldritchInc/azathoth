"""Persistence contracts for reusable goals."""

from typing import Protocol
from uuid import UUID

from azathoth.goals.models import Goal


class GoalRepository(Protocol):
    """Persist and retrieve reusable goals."""

    def save(
        self,
        goal: Goal,
    ) -> None:
        """Persist one goal."""

        ...

    def get(
        self,
        goal_id: UUID,
    ) -> Goal | None:
        """Return one goal by identifier."""

        ...

    def goals(
        self,
    ) -> tuple[Goal, ...]:
        """Return all goals in insertion order."""

        ...
