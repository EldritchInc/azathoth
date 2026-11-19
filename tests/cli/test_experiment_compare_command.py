"""Tests for `azathoth experiment compare`, which prints what promoting a winner would change."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import compare_experiment_command
from azathoth.cli.parsing import build_parser
from azathoth.persistence.repositories import Repositories
from tests.api.test_experiment_comparison import (
    CHEAPER_MODEL,
    keep_runs,
    production_on,
    stocked,
)
from tests.cli.test_experiment_commands import STEP_ID, configure_database
from tests.cli.test_experiment_rendering import (
    FIRST_EXPERIMENT_ID,
    LOSING_OBSERVATION_ID,
    WINNING_OBSERVATION_ID,
    WORKFLOW_ID,
)

UNKNOWN_ID = UUID("00000000-0000-4000-8000-0000000000ff")


@pytest.fixture
def stored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Repositories:
    """Return the repositories of the CLI's database, holding the experiment."""

    return stocked(str(configure_database(monkeypatch, tmp_path)))


def test_the_command_parses() -> None:
    arguments = build_parser().parse_args(["experiment", "compare", str(FIRST_EXPERIMENT_ID)])

    assert arguments.experiment_id == FIRST_EXPERIMENT_ID


def test_the_winner_is_printed_beside_the_baseline_with_what_it_saves(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep_runs(stored)

    assert compare_experiment_command(FIRST_EXPERIMENT_ID) == 0

    out = capsys.readouterr().out.splitlines()

    assert out[:5] == [
        f"Experiment ID: {FIRST_EXPERIMENT_ID}",
        f"Workflow ID: {WORKFLOW_ID}",
        "Compared With: configured",
        f"Winner Observation ID: {WINNING_OBSERVATION_ID}",
        f"Baseline Observation ID: {LOSING_OBSERVATION_ID}",
    ]
    assert f"Step {STEP_ID}: openrouter/example-model -> openrouter/acme/small" in out
    assert "Winner Run: $0.010000, 2.50 s, over 2 runs" in out
    assert "Baseline Run: $0.050000, 5.00 s, over 2 runs" in out
    assert "Saves Per Run: $0.040000 (80.0%), 2.50 s (50.0%)" in out
    assert "Projection: none; production made no invocation in the last 30 days" in out
    assert out[-1] == (
        f"Promote: azathoth workflow promote {WORKFLOW_ID} --experiment {FIRST_EXPERIMENT_ID}"
    )


def test_a_winner_that_costs_more_says_so(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep_runs(stored, winner_costs=(0.10, 0.10), winner_seconds=(6.0, 6.0))

    assert compare_experiment_command(FIRST_EXPERIMENT_ID) == 0

    out = capsys.readouterr().out.splitlines()

    assert "Saves Per Run: costs $0.050000 more (100.0%), takes 1.00 s longer (20.0%)" in out


def test_nothing_to_compare_says_why(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    keep_runs(stored)
    stored.production_states.set(production_on(CHEAPER_MODEL))

    assert compare_experiment_command(FIRST_EXPERIMENT_ID) == 0

    out = capsys.readouterr().out.splitlines()

    assert "Compared With: nothing. Production already runs the winner." in out
    assert not any(line.startswith("Saves Per Run") for line in out)


def test_an_unknown_experiment_is_refused(
    stored: Repositories,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del stored

    assert compare_experiment_command(UNKNOWN_ID) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"Experiment {UNKNOWN_ID} was not found.\n"
