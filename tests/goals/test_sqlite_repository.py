"""Tests for SQLite goal persistence."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.goals import (
    Goal,
    GoalRepository,
    SQLiteGoalRepository,
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
        constraints=(
            "Do not rely on unavailable external state.",
            "Remain provider independent.",
        ),
    )


def test_sqlite_goal_repository_saves_and_gets_goal(
    tmp_path: Path,
) -> None:
    repository = SQLiteGoalRepository(tmp_path / "goals.db")

    goal = create_goal()

    repository.save(goal)

    restored = repository.get(FIRST_GOAL_ID)

    assert restored == goal
    assert restored is not goal


def test_sqlite_goal_repository_returns_none_for_unknown_goal(
    tmp_path: Path,
) -> None:
    repository = SQLiteGoalRepository(tmp_path / "goals.db")

    assert repository.get(FIRST_GOAL_ID) is None


def test_sqlite_goal_repository_preserves_insertion_order(
    tmp_path: Path,
) -> None:
    repository = SQLiteGoalRepository(tmp_path / "goals.db")

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


def test_sqlite_goal_repository_rejects_duplicate_goal(
    tmp_path: Path,
) -> None:
    repository = SQLiteGoalRepository(tmp_path / "goals.db")

    goal = create_goal()

    repository.save(goal)

    with pytest.raises(
        ValueError,
        match=(f"Goal {FIRST_GOAL_ID} already exists"),
    ):
        repository.save(goal)


def test_sqlite_goal_repository_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    goal = create_goal()

    SQLiteGoalRepository(database).save(goal)

    restored = SQLiteGoalRepository(database).get(FIRST_GOAL_ID)

    assert restored == goal
    assert restored is not goal


def test_sqlite_goal_repository_preserves_complete_goal_semantics(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    goal = create_goal()

    SQLiteGoalRepository(database).save(goal)

    restored = SQLiteGoalRepository(database).get(FIRST_GOAL_ID)

    assert restored is not None

    assert restored.id == FIRST_GOAL_ID
    assert restored.name == "Answer accurately"

    assert restored.description == "Produce the correct answer for the request."

    assert restored.success_criteria == (
        "The answer matches the expected result.",
        "The answer remains factual.",
    )

    assert restored.constraints == (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
    )


def test_sqlite_goal_repository_satisfies_protocol(
    tmp_path: Path,
) -> None:
    repository: GoalRepository = require_goal_repository(
        SQLiteGoalRepository(tmp_path / "goals.db")
    )

    assert repository.goals() == ()
