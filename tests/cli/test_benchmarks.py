"""Tests for durable benchmark inspection commands."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    list_benchmark_cases,
    list_benchmarks,
    show_benchmark,
    show_benchmark_case,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

SECOND_BENCHMARK_ID = UUID("22222222-2222-2222-2222-222222222222")

FIRST_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

SECOND_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")

UNKNOWN_CASE_ID = UUID("55555555-5555-5555-5555-555555555555")


def create_dataset(
    *,
    benchmark_id: UUID = BENCHMARK_ID,
    name: str = "classification benchmark",
    version: str = "1.0.0",
) -> BenchmarkDataset:
    """Create one deterministic benchmark dataset."""

    return BenchmarkDataset(
        id=benchmark_id,
        name=name,
        description="Verify deterministic classification behavior.",
        version=version,
        cases=(
            BenchmarkCase(
                id=FIRST_CASE_ID,
                input="good",
                expected=ExpectedOutcome(
                    description="Classify the input as positive.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "positive",
                },
            ),
            BenchmarkCase(
                id=SECOND_CASE_ID,
                input="bad",
                expected=ExpectedOutcome(
                    description="Classify the input as negative.",
                    value="negative",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "negative",
                },
            ),
        ),
    )


def configure_repository(
    *,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    datasets: tuple[BenchmarkDataset, ...],
) -> None:
    """Persist benchmarks and configure the CLI database."""

    repository = SQLiteBenchmarkRepository(
        database,
    )

    for dataset in datasets:
        repository.save(dataset)

    monkeypatch.setenv(
        DATABASE_ENVIRONMENT_VARIABLE,
        str(database),
    )


def test_benchmark_list_prints_datasets_in_durable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(
            create_dataset(),
            create_dataset(
                benchmark_id=SECOND_BENCHMARK_ID,
                name="second benchmark",
                version="2.0.0",
            ),
        ),
    )

    result = list_benchmarks()

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{BENCHMARK_ID}  1.0.0  classification benchmark\n"
        f"{SECOND_BENCHMARK_ID}  2.0.0  second benchmark\n"
    )

    assert captured.err == ""


def test_benchmark_list_prints_nothing_when_repository_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(),
    )

    assert list_benchmarks() == 0

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""


def test_benchmark_show_prints_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(create_dataset(),),
    )

    result = show_benchmark(
        BENCHMARK_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {BENCHMARK_ID}\n" in captured.out
    assert "Name: classification benchmark\n" in captured.out
    assert "Version: 1.0.0\n" in captured.out
    assert "Description: Verify deterministic classification behavior.\n" in captured.out
    assert "Cases: 2\n" in captured.out


def test_benchmark_show_rejects_unknown_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(),
    )

    result = show_benchmark(
        BENCHMARK_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (f"Benchmark dataset {BENCHMARK_ID} is not configured.\n")


def test_benchmark_cases_lists_cases_in_dataset_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(create_dataset(),),
    )

    result = list_benchmark_cases(
        BENCHMARK_ID,
    )

    captured = capsys.readouterr()

    assert result == 0

    assert captured.out == (
        f"{FIRST_CASE_ID}  Classify the input as positive.\n"
        f"{SECOND_CASE_ID}  Classify the input as negative.\n"
    )

    assert captured.err == ""


def test_benchmark_case_show_prints_complete_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(create_dataset(),),
    )

    result = show_benchmark_case(
        BENCHMARK_ID,
        FIRST_CASE_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert f"ID: {FIRST_CASE_ID}\n" in captured.out

    assert "Input:\n" in captured.out
    assert '"good"' in captured.out

    assert "Expected:\n" in captured.out
    assert "  Description: Classify the input as positive.\n" in captured.out
    assert "  Comparison: exact\n" in captured.out
    assert '    "positive"' in captured.out

    assert "Metadata:\n" in captured.out
    assert '"category": "positive"' in captured.out


def test_benchmark_case_show_rejects_unknown_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"

    configure_repository(
        database=database,
        monkeypatch=monkeypatch,
        datasets=(create_dataset(),),
    )

    result = show_benchmark_case(
        BENCHMARK_ID,
        UNKNOWN_CASE_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (
        f"Benchmark case {UNKNOWN_CASE_ID} is not configured in dataset {BENCHMARK_ID}.\n"
    )
