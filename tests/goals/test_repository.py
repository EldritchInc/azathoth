"""Tests for reusable goal repositories."""

from uuid import UUID

import pytest

from azathoth.goals import (
    Goal,
    GoalRepository,
    InMemoryGoalRepository,
    require_goal_repository,
)

FIRST_GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_GOAL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_goal(
    *,
    goal_id: UUID = FIRST_GOAL_ID,
    name: str = "Answer accurately",
) -> Goal:
    """Create one deterministic reusable goal."""

    return Goal(
        id=goal_id,
        name=name,
        description="Produce the correct answer for the request.",
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
        ),
        constraints=("Do not rely on unavailable external state.",),
    )


def test_in_memory_goal_repository_saves_and_gets_goal() -> None:
    repository = InMemoryGoalRepository()

    goal = create_goal()

    repository.save(goal)

    assert repository.get(FIRST_GOAL_ID) is goal


def test_in_memory_goal_repository_returns_none_for_unknown_goal() -> None:
    repository = InMemoryGoalRepository()

    assert repository.get(FIRST_GOAL_ID) is None


def test_in_memory_goal_repository_preserves_insertion_order() -> None:
    repository = InMemoryGoalRepository()

    first = create_goal()

    second = create_goal(
        goal_id=SECOND_GOAL_ID,
        name="Preserve structure",
    )

    repository.save(first)
    repository.save(second)

    assert repository.goals() == (
        first,
        second,
    )


def test_in_memory_goal_repository_rejects_duplicate_goal() -> None:
    repository = InMemoryGoalRepository()

    goal = create_goal()

    repository.save(goal)

    with pytest.raises(
        ValueError,
        match=(f"Goal {FIRST_GOAL_ID} already exists"),
    ):
        repository.save(goal)


def test_goal_repository_satisfies_protocol() -> None:
    repository: GoalRepository = require_goal_repository(InMemoryGoalRepository())

    assert repository.goals() == ()
