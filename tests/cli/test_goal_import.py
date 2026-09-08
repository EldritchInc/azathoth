"""Tests for durable goal import through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    import_goal,
)
from azathoth.goals import (
    Goal,
    SQLiteGoalRepository,
    encode_goal_document,
)

GOAL_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_goal() -> Goal:
    """Create one deterministic imported goal."""

    return Goal(
        id=GOAL_ID,
        name="Answer accurately",
        description=("Produce the correct answer for the supplied request."),
        success_criteria=(
            "The answer matches the expected result.",
            "The answer remains factual.",
        ),
        constraints=("Do not rely on unavailable external state.",),
    )


def configure_database(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure one isolated CLI database."""

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_goal_import_persists_complete_goal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "goal.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    document_path.write_text(
        encode_goal_document(
            create_goal(),
        ),
        encoding="utf-8",
    )

    result = import_goal(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert captured.out == (f"Imported goal {GOAL_ID}.\n")

    repository = SQLiteGoalRepository(
        database,
    )

    assert (
        repository.get(
            GOAL_ID,
        )
        == create_goal()
    )


def test_goal_import_rejects_missing_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "missing.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    result = import_goal(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "Unable to read goal document" in captured.err

    assert not database.exists()


def test_goal_import_rejects_invalid_document_before_creating_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "goal.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    document_path.write_text(
        '{"hello":"eldritch"}',
        encoding="utf-8",
    )

    result = import_goal(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == ("Goal document is not a valid Goal.\n")

    assert not database.exists()


def test_goal_import_rejects_duplicate_goal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "goal.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    repository = SQLiteGoalRepository(
        database,
    )

    repository.save(
        create_goal(),
    )

    document_path.write_text(
        encode_goal_document(
            create_goal(),
        ),
        encoding="utf-8",
    )

    result = import_goal(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Goal {GOAL_ID} already exists.\n")

    assert repository.goals() == (create_goal(),)
