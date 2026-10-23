"""Tests for reconstructing the semantic judge rotation at CLI bootstrap."""

from pathlib import Path

import pytest

from azathoth.cli import (
    CliRuntimeConfiguration,
    load_runtime,
)
from azathoth.evaluation import (
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    SQLiteJudgeRotationRepository,
)
from azathoth.runtime import JudgeUnavailableError

ALPHA = JudgeEntry(
    provider="openrouter",
    model="alpha",
)

BETA = JudgeEntry(
    provider="openrouter",
    model="beta",
)


def test_cli_bootstrap_without_judges_has_empty_rotation(
    tmp_path: Path,
) -> None:
    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=tmp_path / "azathoth.db",
        )
    )

    assert runtime.judges == JudgeRotation()


def test_cli_bootstrap_reconstructs_judge_rotation_in_order(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteJudgeRotationRepository(database)
    repository.add(BETA)
    repository.add(ALPHA)

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    assert runtime.judges.identifiers == (
        "openrouter/beta",
        "openrouter/alpha",
    )


def test_cli_bootstrap_does_not_resolve_unusable_judges(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteJudgeRotationRepository(database).add(ALPHA)

    runtime = load_runtime(
        CliRuntimeConfiguration(
            database=database,
        )
    )

    assert runtime.outcome_evaluator().supports(OutcomeComparison.EXACT)

    with pytest.raises(
        JudgeUnavailableError,
        match="^Judge model openrouter/alpha is not authorized.$",
    ):
        runtime.outcome_evaluator(
            semantic=True,
        )
