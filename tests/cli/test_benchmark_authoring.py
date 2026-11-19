"""Tests for creating a benchmark and editing its cases from the CLI (ADR 0130)."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import main
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.sensitivity import Sensitivity
from tests.cli.test_workflow_run import configure_database

BENCHMARK_ID = UUID("99999999-9999-9999-9999-999999999991")

CASE_ID = UUID("99999999-9999-9999-9999-999999999993")

RESTRICTED_ID = UUID("99999999-9999-9999-9999-999999999994")

UNKNOWN_ID = UUID("99999999-9999-9999-9999-999999999995")


def stock(
    database: Path,
) -> SQLiteBenchmarkRepository:
    """Save one benchmark with an internal case and a restricted one."""

    repository = SQLiteBenchmarkRepository(database)
    repository.save(
        BenchmarkDataset(
            id=BENCHMARK_ID,
            name="Word count",
            description="Count words.",
            cases=(
                BenchmarkCase(
                    id=CASE_ID,
                    input="that is not dead",
                    expected=ExpectedOutcome(
                        description="Four words.", value=4, comparison=OutcomeComparison.EXACT
                    ),
                ),
                BenchmarkCase(
                    id=RESTRICTED_ID,
                    input="which can eternal lie",
                    sensitivity=Sensitivity.RESTRICTED,
                    expected=ExpectedOutcome(
                        description="Four more.", value=4, comparison=OutcomeComparison.EXACT
                    ),
                ),
            ),
        )
    )

    return repository


@pytest.fixture
def repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> SQLiteBenchmarkRepository:
    """Return the CLI's benchmark repository, holding the word count benchmark."""

    return stock(configure_database(monkeypatch, tmp_path))


def latest_case(
    repository: SQLiteBenchmarkRepository,
    case_id: UUID,
) -> BenchmarkCase:
    """Return one case of the benchmark's latest revision."""

    dataset = repository.get(BENCHMARK_ID)

    assert dataset is not None

    return next(case for case in dataset.cases if case.id == case_id)


def test_benchmark_create_saves_an_empty_benchmark_and_names_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(monkeypatch, tmp_path)

    status = main(
        ["benchmark", "create", "--name", "tickets", "--description", "Summarize tickets."]
    )
    out = capsys.readouterr().out

    assert status == 0
    (dataset,) = SQLiteBenchmarkRepository(database).datasets()
    assert dataset.name == "tickets"
    assert dataset.version == "1.0.0"
    assert dataset.cases == ()
    assert out == f"Created benchmark dataset {dataset.id} revision 1.\n"


def test_benchmark_create_refuses_a_blank_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure_database(monkeypatch, tmp_path)

    status = main(["benchmark", "create", "--name", " ", "--description", "Tickets."])

    assert status == 1
    assert "must not be blank" in capsys.readouterr().err
    assert SQLiteBenchmarkRepository(database).datasets() == ()


def test_edit_case_changes_what_it_is_given_as_the_next_revision(
    repository: SQLiteBenchmarkRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        [
            "benchmark",
            "edit-case",
            str(BENCHMARK_ID),
            str(CASE_ID),
            "--comparison",
            "normalized",
            "--expected",
            json.dumps({"words": 4}),
            "--require-citation",
            "poem:l1",
        ]
    )

    assert status == 0, capsys.readouterr().err
    edited = latest_case(repository, CASE_ID)
    assert edited.input == "that is not dead"
    assert edited.expected.comparison is OutcomeComparison.NORMALIZED
    assert edited.expected.value == {"words": 4}
    assert edited.expected.description == "Four words."
    assert edited.expected.citations is not None
    assert [cited.source for cited in edited.expected.citations.require] == ["poem"]
    assert capsys.readouterr().out == (
        f"Edited benchmark case {CASE_ID} in benchmark dataset {BENCHMARK_ID} revision 2.\n"
    )


def test_edit_case_clears_what_the_run_must_cite(
    repository: SQLiteBenchmarkRepository,
) -> None:
    assert (
        main(
            [
                "benchmark",
                "edit-case",
                str(BENCHMARK_ID),
                str(CASE_ID),
                "--require-citation",
                "poem:l1",
            ]
        )
        == 0
    )
    assert main(["benchmark", "edit-case", str(BENCHMARK_ID), str(CASE_ID), "--no-citations"]) == 0

    assert latest_case(repository, CASE_ID).expected.citations is None


def test_edit_case_may_expect_null(
    repository: SQLiteBenchmarkRepository,
) -> None:
    assert (
        main(["benchmark", "edit-case", str(BENCHMARK_ID), str(CASE_ID), "--expected", "null"]) == 0
    )

    assert latest_case(repository, CASE_ID).expected.value is None


def test_edit_case_never_lowers_a_label(
    repository: SQLiteBenchmarkRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(
        [
            "benchmark",
            "edit-case",
            str(BENCHMARK_ID),
            str(RESTRICTED_ID),
            "--sensitivity",
            "internal",
        ]
    )

    assert status == 1
    assert capsys.readouterr().err == (
        f"Benchmark case {RESTRICTED_ID} is restricted; an edit cannot label it internal.\n"
    )
    assert len(repository.revisions(BENCHMARK_ID)) == 1


def test_edit_case_refuses_citations_it_is_told_both_to_name_and_clear(
    repository: SQLiteBenchmarkRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "benchmark",
                "edit-case",
                str(BENCHMARK_ID),
                str(CASE_ID),
                "--require-citation",
                "poem:l1",
                "--no-citations",
            ]
        )

    assert raised.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_remove_case_leaves_the_next_revision_without_it(
    repository: SQLiteBenchmarkRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(["benchmark", "remove-case", str(BENCHMARK_ID), str(RESTRICTED_ID)])

    assert status == 0
    dataset = repository.get(BENCHMARK_ID)
    assert dataset is not None
    assert [case.id for case in dataset.cases] == [CASE_ID]
    assert capsys.readouterr().out == (
        f"Removed benchmark case {RESTRICTED_ID} from benchmark dataset {BENCHMARK_ID} "
        "revision 2.\n"
    )


def test_remove_case_refuses_an_unknown_case(
    repository: SQLiteBenchmarkRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(["benchmark", "remove-case", str(BENCHMARK_ID), str(UNKNOWN_ID)])

    assert status == 1
    assert capsys.readouterr().err == (
        f"Benchmark case {UNKNOWN_ID} is not configured in dataset {BENCHMARK_ID}.\n"
    )
    assert len(repository.revisions(BENCHMARK_ID)) == 1
