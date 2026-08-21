"""Immutable catalogs of reusable goals."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from azathoth.goals.models import Goal


class GoalCatalog(BaseModel):
    """Immutable inventory of configured goals."""

    model_config = ConfigDict(
        frozen=True,
    )

    goals: tuple[
        Goal,
        ...,
    ] = ()

    @property
    def identifiers(
        self,
    ) -> tuple[UUID, ...]:
        """Return goal identifiers in catalog order."""

        return tuple(goal.id for goal in self.goals)

    def get(
        self,
        goal_id: UUID,
    ) -> Goal | None:
        """Return one goal by identifier."""

        return next(
            (goal for goal in self.goals if goal.id == goal_id),
            None,
        )
