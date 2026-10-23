"""Tests for in-memory and SQLite persistence of the semantic judge rotation."""

from pathlib import Path

import pytest

from azathoth.evaluation import (
    InMemoryJudgeRotationRepository,
    JudgeEntry,
    JudgeRotation,
    JudgeRotationRepository,
    SQLiteJudgeRotationRepository,
    require_judge_rotation_repository,
)

ALPHA = JudgeEntry(
    provider="openrouter",
    model="alpha",
)

BETA = JudgeEntry(
    provider="openrouter",
    model="beta",
)


def create_repositories(
    tmp_path: Path,
) -> tuple[JudgeRotationRepository, ...]:
    """Create one repository of each implementation."""

    return (
        require_judge_rotation_repository(
            InMemoryJudgeRotationRepository(),
        ),
        require_judge_rotation_repository(
            SQLiteJudgeRotationRepository(
                tmp_path / "azathoth.db",
            ),
        ),
    )


def test_empty_repository_has_empty_rotation(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        assert repository.rotation() == JudgeRotation()


def test_repository_keeps_judges_in_insertion_order(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.add(BETA)
        repository.add(ALPHA)

        assert repository.rotation() == JudgeRotation(
            entries=(
                BETA,
                ALPHA,
            ),
        )


def test_repository_finds_judge_by_identifier(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.add(ALPHA)

        assert repository.get("openrouter/alpha") == ALPHA
        assert repository.get("openrouter/beta") is None


def test_repository_rejects_duplicate_judge(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.add(ALPHA)

        with pytest.raises(
            ValueError,
            match="^Judge 'openrouter/alpha' is already in the rotation.$",
        ):
            repository.add(ALPHA)

        assert repository.rotation().identifiers == ("openrouter/alpha",)


def test_repository_removes_judge(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.add(ALPHA)
        repository.add(BETA)

        repository.remove("openrouter/alpha")

        assert repository.rotation().identifiers == ("openrouter/beta",)


def test_repository_rejects_removing_unknown_judge(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        with pytest.raises(
            ValueError,
            match="^Judge 'openrouter/alpha' is not in the rotation.$",
        ):
            repository.remove("openrouter/alpha")


def test_removed_judge_can_be_added_back_at_the_end(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.add(ALPHA)
        repository.add(BETA)
        repository.remove("openrouter/alpha")
        repository.add(ALPHA)

        assert repository.rotation().identifiers == (
            "openrouter/beta",
            "openrouter/alpha",
        )


def test_sqlite_rotation_is_durable_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteJudgeRotationRepository(database).add(ALPHA)
    SQLiteJudgeRotationRepository(database).add(BETA)

    assert SQLiteJudgeRotationRepository(database).rotation().identifiers == (
        "openrouter/alpha",
        "openrouter/beta",
    )
