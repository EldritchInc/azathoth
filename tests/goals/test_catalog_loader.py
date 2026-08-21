"""Tests for reconstruction of goal catalogs."""

from pathlib import Path
from uuid import UUID

from azathoth.goals import (
    Goal,
    GoalCatalogLoader,
    InMemoryGoalRepository,
    SQLiteGoalRepository,
)

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
        constraints=("Remain strategy independent.",),
    )


def test_goal_catalog_loader_reconstructs_repository_goals() -> None:
    repository = InMemoryGoalRepository()

    first = create_goal(
        goal_id=FIRST_GOAL_ID,
        name="first goal",
    )

    second = create_goal(
        goal_id=SECOND_GOAL_ID,
        name="second goal",
    )

    repository.save(first)
    repository.save(second)

    catalog = GoalCatalogLoader(repository).load_catalog()

    assert catalog.goals == (
        first,
        second,
    )


def test_goal_catalog_loader_preserves_repository_order() -> None:
    repository = InMemoryGoalRepository()

    second = create_goal(
        goal_id=SECOND_GOAL_ID,
        name="second goal",
    )

    first = create_goal(
        goal_id=FIRST_GOAL_ID,
        name="first goal",
    )

    repository.save(second)
    repository.save(first)

    catalog = GoalCatalogLoader(repository).load_catalog()

    assert catalog.identifiers == (
        SECOND_GOAL_ID,
        FIRST_GOAL_ID,
    )


def test_goal_catalog_loader_returns_empty_catalog() -> None:
    catalog = GoalCatalogLoader(InMemoryGoalRepository()).load_catalog()

    assert catalog.goals == ()


def test_goal_catalog_loader_preserves_complete_goal_semantics() -> None:
    repository = InMemoryGoalRepository()

    goal = Goal(
        id=FIRST_GOAL_ID,
        name="Answer accurately",
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

    repository.save(goal)

    catalog = GoalCatalogLoader(repository).load_catalog()

    restored = catalog.get(FIRST_GOAL_ID)

    assert restored == goal
    assert restored is goal

    assert restored is not None

    assert restored.name == "Answer accurately"

    assert restored.success_criteria == (
        "The answer matches the expected result.",
        "The answer remains factual.",
    )

    assert restored.constraints == (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
    )


def test_goal_catalog_loader_reconstructs_sqlite_repository(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    repository = SQLiteGoalRepository(database)

    first = create_goal(
        goal_id=FIRST_GOAL_ID,
        name="first goal",
    )

    second = create_goal(
        goal_id=SECOND_GOAL_ID,
        name="second goal",
    )

    repository.save(first)
    repository.save(second)

    catalog = GoalCatalogLoader(SQLiteGoalRepository(database)).load_catalog()

    assert catalog.goals == (
        first,
        second,
    )

    assert catalog.identifiers == (
        FIRST_GOAL_ID,
        SECOND_GOAL_ID,
    )
