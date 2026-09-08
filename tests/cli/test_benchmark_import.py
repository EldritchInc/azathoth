"""Tests for durable benchmark import through the CLI."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.cli import (
    DATABASE_ENVIRONMENT_VARIABLE,
    import_benchmark,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
    encode_benchmark_document,
)

BENCHMARK_ID = UUID("11111111-1111-1111-1111-111111111111")

CASE_ID = UUID("22222222-2222-2222-2222-222222222222")


def create_dataset() -> BenchmarkDataset:
    """Create one deterministic imported benchmark."""

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="classification benchmark",
        description="Verify deterministic classification behavior.",
        version="1.0.0",
        cases=(
            BenchmarkCase(
                id=CASE_ID,
                input={
                    "text": "This was excellent.",
                },
                expected=ExpectedOutcome(
                    description="Classify the input as positive.",
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "positive",
                },
            ),
        ),
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


def test_benchmark_import_persists_complete_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "benchmark.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    document_path.write_text(
        encode_benchmark_document(
            create_dataset(),
        ),
        encoding="utf-8",
    )

    result = import_benchmark(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""

    assert captured.out == (f"Imported benchmark dataset {BENCHMARK_ID}.\n")

    repository = SQLiteBenchmarkRepository(
        database,
    )

    assert (
        repository.get(
            BENCHMARK_ID,
        )
        == create_dataset()
    )


def test_benchmark_import_rejects_missing_document(
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

    result = import_benchmark(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "Unable to read benchmark document" in captured.err

    assert not database.exists()


def test_benchmark_import_rejects_invalid_document_before_creating_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "benchmark.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    document_path.write_text(
        '{"hello":"eldritch"}',
        encoding="utf-8",
    )

    result = import_benchmark(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == ("Benchmark document is not a valid BenchmarkDataset.\n")

    assert not database.exists()


def test_benchmark_import_rejects_duplicate_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "azathoth.db"
    document_path = tmp_path / "benchmark.json"

    configure_database(
        database=database,
        monkeypatch=monkeypatch,
    )

    repository = SQLiteBenchmarkRepository(
        database,
    )

    repository.save(
        create_dataset(),
    )

    document_path.write_text(
        encode_benchmark_document(
            create_dataset(),
        ),
        encoding="utf-8",
    )

    result = import_benchmark(
        document_path,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""

    assert captured.err == (f"Benchmark dataset {BENCHMARK_ID} already exists.\n")

    assert repository.datasets() == (create_dataset(),)
