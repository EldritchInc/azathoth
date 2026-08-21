"""Tests for immutable goal catalogs."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.goals import Goal, GoalCatalog

FIRST_GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_GOAL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_goal(
    *,
    goal_id: UUID,
    name: str,
) -> Goal:
    """Create one deterministic reusable goal."""

    return Goal(
        id=goal_id,
        name=name,
        description=f"Achieve the objective {name}.",
        success_criteria=(f"The objective {name} is satisfied.",),
        constraints=("Remain provider independent.",),
    )


def test_goal_catalog_preserves_goal_order() -> None:
    first = create_goal(
        goal_id=FIRST_GOAL_ID,
        name="first goal",
    )

    second = create_goal(
        goal_id=SECOND_GOAL_ID,
        name="second goal",
    )

    catalog = GoalCatalog(
        goals=(
            first,
            second,
        )
    )

    assert catalog.goals == (
        first,
        second,
    )

    assert catalog.identifiers == (
        FIRST_GOAL_ID,
        SECOND_GOAL_ID,
    )


def test_goal_catalog_gets_goal_by_identifier() -> None:
    goal = create_goal(
        goal_id=FIRST_GOAL_ID,
        name="first goal",
    )

    catalog = GoalCatalog(goals=(goal,))

    assert catalog.get(FIRST_GOAL_ID) is goal


def test_goal_catalog_returns_none_for_unknown_goal() -> None:
    catalog = GoalCatalog()

    assert catalog.get(FIRST_GOAL_ID) is None


def test_goal_catalog_is_immutable() -> None:
    catalog = GoalCatalog()

    with pytest.raises(ValidationError):
        catalog.goals = (
            create_goal(
                goal_id=FIRST_GOAL_ID,
                name="first goal",
            ),
        )
