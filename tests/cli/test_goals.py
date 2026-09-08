"""Tests for durable goal inspection commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_goals,
    show_goal,
)
from azathoth.goals import (
    Goal,
    SQLiteGoalRepository,
)

FIRST_GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_GOAL_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_goal(
    *,
    goal_id: UUID = FIRST_GOAL_ID,
    name: str = "Answer accurately",
    constraints: tuple[str, ...] = (
        "Do not rely on unavailable external state.",
        "Remain provider independent.",
    ),
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
        constraints=constraints,
    )


def configure_repository(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    goals: tuple[Goal, ...],
) -> None:
    """Persist goals and configure the CLI database."""

    repository = SQLiteGoalRepository(
        database,
    )

    for goal in goals:
        repository.save(goal)

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_goal_list_prints_goals_in_durable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        goals=(
            create_goal(),
            create_goal(
                goal_id=SECOND_GOAL_ID,
                name="Preserve structure",
            ),
        ),
    )

    result = list_goals()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{FIRST_GOAL_ID}  Answer accurately\n{SECOND_GOAL_ID}  Preserve structure\n"
    )

    assert captured.err == ""


def test_goal_list_prints_nothing_when_repository_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        goals=(),
    )

    assert list_goals() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_goal_show_prints_complete_goal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        goals=(create_goal(),),
    )

    result = show_goal(
        FIRST_GOAL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {FIRST_GOAL_ID}\n" in captured.out
    assert "Name: Answer accurately\n" in captured.out

    assert "Description: Produce the correct answer for the request.\n" in captured.out

    assert "Success Criteria:\n" in captured.out

    assert "  - The answer matches the expected result.\n" in captured.out

    assert "  - The answer remains factual.\n" in captured.out

    assert "Constraints:\n" in captured.out

    assert "  - Do not rely on unavailable external state.\n" in captured.out

    assert "  - Remain provider independent.\n" in captured.out


def test_goal_show_prints_explicit_empty_constraints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        goals=(
            create_goal(
                constraints=(),
            ),
        ),
    )

    result = show_goal(
        FIRST_GOAL_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert "Constraints:\n" in captured.out
    assert "  None\n" in captured.out


def test_goal_show_rejects_unknown_goal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        goals=(),
    )

    result = show_goal(
        FIRST_GOAL_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Goal {FIRST_GOAL_ID} is not configured.\n")
