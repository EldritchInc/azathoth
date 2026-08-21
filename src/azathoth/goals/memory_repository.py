"""Deterministic in-memory persistence for reusable goals."""

from uuid import UUID

from azathoth.goals.models import Goal
from azathoth.goals.repository import GoalRepository


class InMemoryGoalRepository:
    """Store immutable goals in insertion order."""

    def __init__(
        self,
    ) -> None:
        self._goals: dict[
            UUID,
            Goal,
        ] = {}

    def save(
        self,
        goal: Goal,
    ) -> None:
        """Persist one goal without replacing existing configuration."""

        if goal.id in self._goals:
            raise ValueError(f"Goal {goal.id} already exists.")

        self._goals[goal.id] = goal

    def get(
        self,
        goal_id: UUID,
    ) -> Goal | None:
        """Return one goal by identifier."""

        return self._goals.get(goal_id)

    def goals(
        self,
    ) -> tuple[Goal, ...]:
        """Return all goals in insertion order."""

        return tuple(self._goals.values())


def require_goal_repository(
    repository: GoalRepository,
) -> GoalRepository:
    """Return a repository after static protocol validation."""

    return repository
