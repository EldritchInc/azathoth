"""Tests for revisioned benchmark dataset repositories."""

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.evaluation import (
    BenchmarkDataset,
    BenchmarkDatasetRevision,
    BenchmarkRepository,
    InMemoryBenchmarkRepository,
    SQLiteBenchmarkRepository,
    earliest_identical_benchmark_revision,
    require_benchmark_repository,
)
from azathoth.revisions import content_digest
from tests.cli.test_benchmark_import import (
    BENCHMARK_ID,
    create_dataset,
)


def create_changed_dataset() -> BenchmarkDataset:
    """Create the benchmark with changed content and no cases."""

    return create_dataset().model_copy(
        update={
            "description": "Changed benchmark.",
            "cases": (),
        },
    )


def create_repositories(
    tmp_path: Path,
) -> tuple[BenchmarkRepository, ...]:
    """Return one empty repository of each implementation."""

    return (
        require_benchmark_repository(InMemoryBenchmarkRepository()),
        require_benchmark_repository(SQLiteBenchmarkRepository(tmp_path / "azathoth.db")),
    )


def create_legacy_database(
    database: Path,
    dataset: BenchmarkDataset,
) -> None:
    """Write a database in the layout used before benchmark revisions."""

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            CREATE TABLE benchmark_datasets (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            INSERT INTO benchmark_datasets (
                dataset_id,
                name,
                version,
                payload
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                str(dataset.id),
                dataset.name,
                dataset.version,
                dataset.model_dump_json(),
            ),
        )

        connection.commit()
    finally:
        connection.close()


def test_revisions_record_their_benchmark_and_digest() -> None:
    revision = BenchmarkDatasetRevision.create(
        create_dataset(),
        number=1,
    )

    assert revision.dataset_id == BENCHMARK_ID
    assert revision.content_digest == content_digest(create_dataset())


def test_revision_datasets_must_belong_to_their_benchmark() -> None:
    with pytest.raises(
        ValidationError,
        match="Benchmark revision dataset must belong to its benchmark.",
    ):
        BenchmarkDatasetRevision(
            dataset_id=create_dataset().cases[0].id,
            number=1,
            dataset=create_dataset(),
            content_digest=content_digest(create_dataset()),
        )


def test_earliest_identical_revision_names_the_revert() -> None:
    first = BenchmarkDatasetRevision.create(create_dataset(), number=1)
    changed = BenchmarkDatasetRevision.create(create_changed_dataset(), number=2)
    reverted = BenchmarkDatasetRevision.create(create_dataset(), number=3)

    history = (first, changed, reverted)

    assert earliest_identical_benchmark_revision(history, reverted) == first
    assert earliest_identical_benchmark_revision(history, changed) is None
    assert earliest_identical_benchmark_revision(history, first) is None


def test_saves_append_numbered_revisions(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        saved = (
            repository.save(create_dataset()),
            repository.save(create_changed_dataset()),
            repository.save(create_dataset()),
        )

        assert tuple(revision.number for revision in saved) == (1, 2, 3)
        assert repository.revisions(BENCHMARK_ID) == saved
        assert saved[2].content_digest == saved[0].content_digest


def test_the_latest_revision_is_the_current_dataset(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save(create_dataset())
        latest = repository.save(create_changed_dataset())

        assert repository.get(BENCHMARK_ID) == create_changed_dataset()
        assert repository.datasets() == (create_changed_dataset(),)
        assert repository.latest_revision(BENCHMARK_ID) == latest


def test_revisions_are_found_by_number(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save(create_dataset())
        repository.save(create_changed_dataset())

        assert repository.revision(BENCHMARK_ID, 1) == first
        assert repository.revision(BENCHMARK_ID, 3) is None


def test_sqlite_migrates_legacy_datasets_as_first_revisions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    create_legacy_database(
        database,
        create_dataset(),
    )

    repository = SQLiteBenchmarkRepository(database)

    (revision,) = repository.revisions(BENCHMARK_ID)

    assert revision.number == 1
    assert revision.imported_at is None
    assert repository.get(BENCHMARK_ID) == create_dataset()


def test_sqlite_migration_runs_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    create_legacy_database(
        database,
        create_dataset(),
    )

    SQLiteBenchmarkRepository(database).save(create_changed_dataset())

    reopened = SQLiteBenchmarkRepository(database)

    assert tuple(revision.number for revision in reopened.revisions(BENCHMARK_ID)) == (1, 2)
    assert reopened.get(BENCHMARK_ID) == create_changed_dataset()


def test_sqlite_revisions_survive_reopening(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    saved = (
        SQLiteBenchmarkRepository(database).save(create_dataset()),
        SQLiteBenchmarkRepository(database).save(create_changed_dataset()),
    )

    assert SQLiteBenchmarkRepository(database).revisions(BENCHMARK_ID) == saved
