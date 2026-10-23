"""Tests for refusing to deauthorize a model in the semantic judge rotation."""

from pathlib import Path

import pytest

from azathoth.cli import deauthorize_model
from azathoth.evaluation import (
    JudgeEntry,
    SQLiteJudgeRotationRepository,
)
from tests.cli.test_model_deauthorize_guard import (
    ENTRY,
    configure_runtime,
)


def add_entry_as_judge(
    database: Path,
) -> SQLiteJudgeRotationRepository:
    """Put the guarded model into the judge rotation."""

    repository = SQLiteJudgeRotationRepository(database)

    repository.add(
        JudgeEntry(
            provider=ENTRY.provider,
            model=ENTRY.model,
        )
    )

    return repository


def test_deauthorize_refuses_semantic_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    portfolio = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    judges = add_entry_as_judge(database)

    result = deauthorize_model(ENTRY.identifier)

    captured = capsys.readouterr()

    assert result == 1
    assert portfolio.entries() == (ENTRY,)
    assert judges.rotation().identifiers == (ENTRY.identifier,)
    assert captured.out == ""
    assert captured.err == "\n".join(
        (
            f"Model {ENTRY.identifier!r} is a semantic judge and was not deauthorized.",
            f"Remove it from the rotation first with: azathoth judge remove {ENTRY.identifier}",
            "",
        )
    )


def test_deauthorize_refuses_semantic_judge_even_when_forced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    portfolio = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    add_entry_as_judge(database)

    assert deauthorize_model(ENTRY.identifier, force=True) == 1
    assert portfolio.entries() == (ENTRY,)

    capsys.readouterr()


def test_deauthorize_succeeds_after_judge_is_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    portfolio = configure_runtime(
        monkeypatch=monkeypatch,
        database=database,
    )

    add_entry_as_judge(database).remove(ENTRY.identifier)

    assert deauthorize_model(ENTRY.identifier) == 0
    assert portfolio.entries() == ()

    captured = capsys.readouterr()

    assert captured.out == f"Deauthorized model {ENTRY.identifier}.\n"
