"""End-to-end optimization examples from durable goals."""

from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import ExpectedOutcome, OutcomeComparison
from azathoth.goals import (
    Goal,
    GoalCatalogLoader,
    SQLiteGoalRepository,
)
from azathoth.optimization import OptimizationExample

GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")

EXAMPLE_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_goal() -> Goal:
    """Create one deterministic reusable optimization goal."""

    return Goal(
        id=GOAL_ID,
        name="Answer accurately",
        description=("Produce the correct answer while preserving required behavior."),
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
            "The required output structure is preserved.",
        ),
        constraints=(
            "Do not rely on unavailable external state.",
            "Remain provider independent.",
            "Do not violate the required output contract.",
        ),
    )


def persist_goal(
    database: Path,
) -> None:
    """Persist the canonical reusable goal."""

    SQLiteGoalRepository(database).save(create_goal())


def reconstruct_goal(
    database: Path,
) -> Goal:
    """Reconstruct the durable goal through the public catalog path."""

    catalog = GoalCatalogLoader(SQLiteGoalRepository(database)).load_catalog()

    goal = catalog.get(GOAL_ID)

    assert goal is not None

    return goal


def create_example(
    goal: Goal,
) -> OptimizationExample:
    """Create an optimization example from a reusable goal."""

    return OptimizationExample(
        id=EXAMPLE_ID,
        name="durable goal example",
        goal=goal,
        context=Context(),
        expected_outcome=ExpectedOutcome(
            description="Return the expected answer.",
            value="correct",
            comparison=OutcomeComparison.EXACT,
        ),
        tags=(
            "durable",
            "goal",
        ),
    )


def test_durable_goal_reconstructs_after_repository_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    original = create_goal()

    SQLiteGoalRepository(database).save(original)

    restored = reconstruct_goal(database)

    assert restored == original
    assert restored is not original

    assert restored.id == GOAL_ID
    assert restored.name == "Answer accurately"

    assert restored.description == "Produce the correct answer while preserving required behavior."


def test_durable_goal_preserves_success_criteria(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    persist_goal(database)

    restored = reconstruct_goal(database)

    assert restored.success_criteria == (
        "The answer matches the expected result.",
        "The answer remains factual.",
        "The required output structure is preserved.",
    )


def test_durable_goal_preserves_constraints(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    persist_goal(database)

    restored = reconstruct_goal(database)

    assert restored.constraints == (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
        "Do not violate the required output contract.",
    )


def test_reconstructed_goal_builds_optimization_example(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    persist_goal(database)

    restored = reconstruct_goal(database)

    example = create_example(restored)

    assert example.id == EXAMPLE_ID
    assert example.goal == restored
    assert example.goal.id == GOAL_ID

    assert example.goal.success_criteria == (
        "The answer matches the expected result.",
        "The answer remains factual.",
        "The required output structure is preserved.",
    )

    assert example.goal.constraints == (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
        "Do not violate the required output contract.",
    )

    assert example.tags == (
        "durable",
        "goal",
    )


def test_optimization_example_preserves_reconstructed_goal_snapshot(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    persist_goal(database)

    restored = reconstruct_goal(database)

    example = create_example(restored)

    assert example.goal == restored

    assert example.goal.model_dump() == {
        "id": GOAL_ID,
        "name": "Answer accurately",
        "description": ("Produce the correct answer while preserving required behavior."),
        "success_criteria": (
            "The answer matches the expected result.",
            "The answer remains factual.",
            "The required output structure is preserved.",
        ),
        "constraints": (
            "Do not rely on unavailable external state.",
            "Remain provider independent.",
            "Do not violate the required output contract.",
        ),
    }


def test_durable_goal_can_seed_multiple_optimization_examples(
    tmp_path: Path,
) -> None:
    database = tmp_path / "goals.db"

    persist_goal(database)

    restored = reconstruct_goal(database)

    first = create_example(restored)

    second = OptimizationExample(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        name="second durable goal example",
        goal=restored,
        context=Context(),
        expected_outcome=ExpectedOutcome(
            description="Return another expected answer.",
            value="another correct answer",
            comparison=OutcomeComparison.EXACT,
        ),
        tags=(
            "durable",
            "second-example",
        ),
    )

    assert first.goal == restored
    assert second.goal == restored

    assert first.goal.id == second.goal.id
    assert first.goal.success_criteria == second.goal.success_criteria
    assert first.goal.constraints == second.goal.constraints

    assert first.expected_outcome != second.expected_outcome
