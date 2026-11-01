"""Tests for recording idempotency keys with production invocations (ADR 0097)."""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.workflows import (
    IdempotencyKeyInUseError,
    InMemoryProductionInvocationRepository,
    InvocationIdempotency,
    ProductionInvocation,
    ProductionInvocationRepository,
    ProductionInvocationSuccess,
    SQLiteProductionInvocationRepository,
)

FIRST_INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_INVOCATION_ID = UUID("22222222-2222-2222-2222-222222222222")
THIRD_INVOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")

FIRST_WORKFLOW_ID = UUID("33333333-3333-3333-3333-333333333333")
SECOND_WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

KEY = "order-4711-review"
OTHER_KEY = "order-4712-review"

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64

RepositoryFactory = Callable[[Path], ProductionInvocationRepository]


def create_invocation(
    *,
    invocation_id: UUID = FIRST_INVOCATION_ID,
    workflow_id: UUID = FIRST_WORKFLOW_ID,
    key: str | None = KEY,
    request_digest: str = DIGEST,
) -> ProductionInvocation:
    """Create one deterministic production invocation, keyed unless told otherwise."""

    return ProductionInvocation(
        id=invocation_id,
        workflow_id=workflow_id,
        initial_context=Context(),
        idempotency=(
            InvocationIdempotency(
                key=key,
                request_digest=request_digest,
            )
            if key is not None
            else None
        ),
    )


def in_memory_repository(
    tmp_path: Path,
) -> ProductionInvocationRepository:
    """Create an in-memory repository; the path is unused."""

    return InMemoryProductionInvocationRepository()


def sqlite_repository(
    tmp_path: Path,
) -> ProductionInvocationRepository:
    """Create a SQLite repository in the test's directory."""

    return SQLiteProductionInvocationRepository(
        tmp_path / "production.db",
    )


REPOSITORIES = pytest.mark.parametrize(
    "create_repository",
    [in_memory_repository, sqlite_repository],
    ids=["memory", "sqlite"],
)


# Both repositories


@REPOSITORIES
def test_an_unknown_key_finds_nothing(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    repository.save(create_invocation())

    assert repository.invocation_for_idempotency_key(OTHER_KEY) is None


@REPOSITORIES
def test_a_key_finds_its_invocation(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    second = create_invocation(
        invocation_id=SECOND_INVOCATION_ID,
        workflow_id=SECOND_WORKFLOW_ID,
        key=OTHER_KEY,
        request_digest=OTHER_DIGEST,
    )

    repository.save(first)
    repository.save(second)

    assert repository.invocation_for_idempotency_key(KEY) == first
    assert repository.invocation_for_idempotency_key(OTHER_KEY) == second


@REPOSITORIES
def test_invocations_without_keys_are_never_found_by_key_and_may_be_many(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation(key=None)
    second = create_invocation(invocation_id=SECOND_INVOCATION_ID, key=None)

    repository.save(first)
    repository.save(second)

    assert repository.invocations() == (first, second)
    assert repository.invocation_for_idempotency_key("") is None
    assert repository.invocation_for_idempotency_key("None") is None


@REPOSITORIES
def test_a_used_key_is_refused_and_nothing_is_saved(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    repository.save(first)

    with pytest.raises(IdempotencyKeyInUseError) as raised:
        repository.save(
            create_invocation(
                invocation_id=SECOND_INVOCATION_ID,
                request_digest=OTHER_DIGEST,
            )
        )

    assert raised.value.key == KEY
    assert repository.invocations() == (first,)
    assert repository.get(SECOND_INVOCATION_ID) is None
    assert repository.invocation_for_idempotency_key(KEY) == first


@REPOSITORIES
def test_keys_are_global_across_workflows(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    repository.save(create_invocation())

    with pytest.raises(IdempotencyKeyInUseError):
        repository.save(
            create_invocation(
                invocation_id=SECOND_INVOCATION_ID,
                workflow_id=SECOND_WORKFLOW_ID,
            )
        )

    assert repository.invocations_for_workflow(SECOND_WORKFLOW_ID) == ()


@REPOSITORIES
def test_saving_one_invocation_twice_is_a_duplicate_not_a_key_conflict(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()

    repository.save(invocation)

    with pytest.raises(ValueError, match=f"{FIRST_INVOCATION_ID} already exists") as raised:
        repository.save(invocation)

    assert not isinstance(raised.value, IdempotencyKeyInUseError)


@REPOSITORIES
def test_a_refused_key_leaves_later_saves_working(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    first = create_invocation()

    repository.save(first)

    with pytest.raises(IdempotencyKeyInUseError):
        repository.save(create_invocation(invocation_id=SECOND_INVOCATION_ID))

    later = create_invocation(invocation_id=THIRD_INVOCATION_ID, key=OTHER_KEY)

    repository.save(later)

    assert repository.invocations() == (first, later)


@REPOSITORIES
def test_a_keyed_invocation_takes_one_result(
    tmp_path: Path,
    create_repository: RepositoryFactory,
) -> None:
    repository = create_repository(tmp_path)

    invocation = create_invocation()

    repository.save(invocation)

    result = ProductionInvocationSuccess(
        invocation_id=invocation.id,
        result={"verdict": "approve"},
    )

    repository.save_result(result)

    found = repository.invocation_for_idempotency_key(KEY)

    assert found is not None
    assert repository.result(found.id) == result


def test_idempotency_key_in_use_is_a_value_error_naming_the_key() -> None:
    error = IdempotencyKeyInUseError(KEY)

    assert isinstance(error, ValueError)
    assert error.key == KEY
    assert repr(KEY) in str(error)


# SQLite


def table_columns(
    database: Path,
) -> tuple[str, ...]:
    """Return the invocation table's column names in order."""

    connection = sqlite3.connect(database)

    try:
        return tuple(
            row[1]
            for row in connection.execute(
                """
                PRAGMA table_info(production_invocations)
                """
            ).fetchall()
        )
    finally:
        connection.close()


def table_indexes(
    database: Path,
) -> dict[str, bool]:
    """Return the invocation table's index names and whether each is unique."""

    connection = sqlite3.connect(database)

    try:
        return {
            row[1]: bool(row[2])
            for row in connection.execute(
                """
                PRAGMA index_list(production_invocations)
                """
            ).fetchall()
        }
    finally:
        connection.close()


def create_pre_0097_table(
    database: Path,
    invocations: tuple[ProductionInvocation, ...],
) -> None:
    """Create the invocation table as it was before ADR 0097, with rows."""

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            CREATE TABLE production_invocations (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                invocation_id TEXT NOT NULL UNIQUE,
                workflow_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )

        for invocation in invocations:
            connection.execute(
                """
                INSERT INTO production_invocations (
                    invocation_id,
                    workflow_id,
                    payload
                )
                VALUES (?, ?, ?)
                """,
                (
                    str(invocation.id),
                    str(invocation.workflow_id),
                    invocation.model_dump_json(
                        exclude={"idempotency"},
                    ),
                ),
            )

        connection.commit()
    finally:
        connection.close()


def test_a_new_database_has_the_idempotency_columns_and_unique_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    SQLiteProductionInvocationRepository(database)

    assert table_columns(database) == (
        "sequence",
        "invocation_id",
        "workflow_id",
        "payload",
        "idempotency_key",
        "request_digest",
    )

    assert table_indexes(database)["production_invocations_idempotency_key"] is True


def test_the_key_and_digest_are_written_to_their_columns(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    repository = SQLiteProductionInvocationRepository(database)

    repository.save(create_invocation())
    repository.save(create_invocation(invocation_id=SECOND_INVOCATION_ID, key=None))

    connection = sqlite3.connect(database)

    try:
        rows = connection.execute(
            """
            SELECT invocation_id, idempotency_key, request_digest
            FROM production_invocations
            ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        (str(FIRST_INVOCATION_ID), KEY, DIGEST),
        (str(SECOND_INVOCATION_ID), None, None),
    ]


def test_a_key_survives_repository_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    invocation = create_invocation()

    SQLiteProductionInvocationRepository(database).save(invocation)

    reconstructed = SQLiteProductionInvocationRepository(database)

    assert reconstructed.invocation_for_idempotency_key(KEY) == invocation

    with pytest.raises(IdempotencyKeyInUseError):
        reconstructed.save(create_invocation(invocation_id=SECOND_INVOCATION_ID))


def test_two_repositories_on_one_database_settle_a_key_race(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    first_process = SQLiteProductionInvocationRepository(database)
    second_process = SQLiteProductionInvocationRepository(database)

    winner = create_invocation()

    first_process.save(winner)

    with pytest.raises(IdempotencyKeyInUseError):
        second_process.save(
            create_invocation(
                invocation_id=SECOND_INVOCATION_ID,
            )
        )

    assert second_process.invocation_for_idempotency_key(KEY) == winner
    assert second_process.invocations() == (winner,)


def test_a_pre_0097_table_gains_the_columns_and_keeps_its_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    first = create_invocation(key=None)
    second = create_invocation(invocation_id=SECOND_INVOCATION_ID, key=None)

    create_pre_0097_table(database, (first, second))

    repository = SQLiteProductionInvocationRepository(database)

    assert table_columns(database) == (
        "sequence",
        "invocation_id",
        "workflow_id",
        "payload",
        "idempotency_key",
        "request_digest",
    )

    assert table_indexes(database)["production_invocations_idempotency_key"] is True

    assert repository.invocations() == (first, second)
    assert repository.get(FIRST_INVOCATION_ID) == first
    assert repository.invocation_for_idempotency_key(KEY) is None

    keyed = create_invocation(invocation_id=THIRD_INVOCATION_ID)

    repository.save(keyed)

    assert repository.invocations() == (first, second, keyed)
    assert repository.invocation_for_idempotency_key(KEY) == keyed

    connection = sqlite3.connect(database)

    try:
        sequences = connection.execute(
            """
            SELECT sequence, invocation_id
            FROM production_invocations
            ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()

    assert sequences == [
        (1, str(FIRST_INVOCATION_ID)),
        (2, str(SECOND_INVOCATION_ID)),
        (3, str(THIRD_INVOCATION_ID)),
    ]


def test_migrating_an_already_migrated_table_changes_nothing(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    first = create_invocation(key=None)

    create_pre_0097_table(database, (first,))

    SQLiteProductionInvocationRepository(database)

    columns = table_columns(database)

    repository = SQLiteProductionInvocationRepository(database)

    assert table_columns(database) == columns
    assert repository.invocations() == (first,)


def test_a_table_with_only_the_key_column_gains_the_digest_column(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"

    create_pre_0097_table(database, ())

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            ALTER TABLE production_invocations ADD COLUMN idempotency_key TEXT
            """
        )

        connection.commit()
    finally:
        connection.close()

    SQLiteProductionInvocationRepository(database)

    assert table_columns(database)[-2:] == (
        "idempotency_key",
        "request_digest",
    )
