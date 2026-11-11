"""Tests of the schema's versions: what each adds, and how `initialize` upgrades (ADR 0105).

A version only adds tables. Version 1 is the schema of 1.1 before resume;
version 2 adds the tables that record a run while it executes; version 3
adds the tables that record revision lineage and portfolio provenance
(ADR 0122); version 4 adds the table that records who declared each
portfolio entry's data policy (ADR 0123); version 5 adds the table of a
remote's tokens (ADR 0124). A table added without a new version, or a
version that drops a table, fails here.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.persistence import (
    SCHEMA_TABLE,
    SCHEMA_VERSION,
    Database,
    DatabaseSchemaOutdatedError,
    DatabaseSchemaTooNewError,
    InitializationOutcome,
    IntegrityError,
    Parameter,
    PostgresDatabase,
    SQLiteDatabase,
    Table,
)
from azathoth.persistence.repositories import SCHEMA_TABLES
from azathoth.providers import MODEL_PORTFOLIO_POLICY_TABLES, MODEL_PORTFOLIO_PROVENANCE_TABLES
from azathoth.remote import REMOTE_TOKEN_TABLES
from azathoth.revisions import (
    REVISION_LINEAGE_TABLES,
    Lineage,
    LineageRecord,
    RevisionKind,
    lineage_records,
    revision_digest,
)
from azathoth.workflows import (
    RUN_CHILD_TABLES,
    RUN_JOURNAL_TABLES,
    RUN_LEASE_TABLES,
    RUN_PROGRESS_TABLES,
)

VERSION_1_TABLE_NAMES = (
    "workflow_specification_revisions",
    "workflow_production_states",
    "workflow_production_revisions",
    "workflow_runs",
    "workflow_run_evaluations",
    "workflow_run_feedback",
    "workflow_experiments",
    "workflow_experiment_observations",
    "workflow_benchmark_executions",
    "workflow_benchmark_execution_cases",
    "production_invocations",
    "production_invocation_results",
    "production_invocation_runs",
    "tool_definitions",
    "tool_implementations",
    "tool_test_cases",
    "tool_document_revisions",
    "benchmark_dataset_revisions",
    "goals",
    "judge_rotation_entries",
    "models",
    "model_portfolio_entries",
    "provider_model_observations",
    "content_blobs",
)

VERSION_2_TABLE_NAMES = (
    "run_journal",
    "run_leases",
    "run_children",
)

VERSION_3_TABLE_NAMES = (
    "revision_lineage",
    "model_portfolio_provenance",
)

VERSION_4_TABLE_NAMES = ("model_portfolio_policy_declarations",)

VERSION_5_TABLE_NAMES = ("remote_tokens",)

VERSION_3_TABLES = (*REVISION_LINEAGE_TABLES, *MODEL_PORTFOLIO_PROVENANCE_TABLES)

VERSION_4_TABLES = MODEL_PORTFOLIO_POLICY_TABLES

VERSION_5_TABLES = REMOTE_TOKEN_TABLES

VERSION_4_SCHEMA = tuple(table for table in SCHEMA_TABLES if table not in VERSION_5_TABLES)

VERSION_3_SCHEMA = tuple(table for table in VERSION_4_SCHEMA if table not in VERSION_4_TABLES)

VERSION_2_TABLES = tuple(table for table in VERSION_3_SCHEMA if table not in VERSION_3_TABLES)

VERSION_1_TABLES = tuple(table for table in VERSION_2_TABLES if table not in RUN_PROGRESS_TABLES)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC).isoformat()

RUN_ID = "a0000000-0000-4000-8000-000000000001"

WORKFLOW_ID = "a0000000-0000-4000-8000-000000000002"


def names(
    tables: tuple[Table, ...],
) -> tuple[str, ...]:
    """Return the names of the tables, in order."""

    return tuple(table.name for table in tables)


def has_table(
    database: Database,
    name: str,
) -> bool:
    """Return whether the database holds a table of this name."""

    with database.transaction() as session:
        if isinstance(database, PostgresDatabase):
            return session.fetchone("SELECT to_regclass(?)", (name,)) != (None,)

        return (
            session.fetchone(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            )
            is not None
        )


def record_version(
    database: PostgresDatabase,
    version: int,
) -> None:
    """Overwrite the schema version a PostgreSQL database records."""

    with database.transaction() as session:
        session.execute(f"UPDATE {SCHEMA_TABLE} SET version = ? WHERE id = 1", (version,))


def recorded_version(
    database: PostgresDatabase,
) -> object:
    """Return the schema version a PostgreSQL database records."""

    with database.transaction() as session:
        row = session.fetchone(f"SELECT version FROM {SCHEMA_TABLE} WHERE id = 1")

    assert row is not None

    return row[0]


def initialize_version_1(
    database: PostgresDatabase,
) -> None:
    """Initialize a PostgreSQL database as an Azathoth of schema version 1 did."""

    database.initialize(VERSION_1_TABLES)
    record_version(database, 1)


def initialize_version_2(
    database: PostgresDatabase,
) -> None:
    """Initialize a PostgreSQL database as an Azathoth of schema version 2 did."""

    database.initialize(VERSION_2_TABLES)
    record_version(database, 2)


def initialize_version_3(
    database: PostgresDatabase,
) -> None:
    """Initialize a PostgreSQL database as an Azathoth of schema version 3 did."""

    database.initialize(VERSION_3_SCHEMA)
    record_version(database, 3)


def initialize_version_4(
    database: PostgresDatabase,
) -> None:
    """Initialize a PostgreSQL database as an Azathoth of schema version 4 did."""

    database.initialize(VERSION_4_SCHEMA)
    record_version(database, 4)


def execute(
    database: Database,
    statement: str,
    parameters: tuple[Parameter, ...],
) -> None:
    """Execute one statement in a transaction of its own."""

    with database.transaction() as session:
        session.execute(statement, parameters)


# What each version holds


def test_this_azathoth_uses_schema_version_5() -> None:
    assert SCHEMA_VERSION == 5


def test_version_1_holds_the_tables_of_1_1() -> None:
    assert names(VERSION_1_TABLES) == VERSION_1_TABLE_NAMES


def test_version_2_adds_the_run_progress_tables_after_every_earlier_table() -> None:
    assert names(VERSION_2_TABLES) == VERSION_1_TABLE_NAMES + VERSION_2_TABLE_NAMES
    assert names(RUN_PROGRESS_TABLES) == VERSION_2_TABLE_NAMES
    assert RUN_PROGRESS_TABLES == RUN_JOURNAL_TABLES + RUN_LEASE_TABLES + RUN_CHILD_TABLES


def test_version_3_adds_lineage_and_provenance_after_every_earlier_table() -> None:
    assert names(VERSION_3_SCHEMA) == (
        VERSION_1_TABLE_NAMES + VERSION_2_TABLE_NAMES + VERSION_3_TABLE_NAMES
    )
    assert names(VERSION_3_TABLES) == VERSION_3_TABLE_NAMES


def test_version_4_adds_policy_declarations_after_every_earlier_table() -> None:
    assert names(VERSION_4_SCHEMA) == (
        VERSION_1_TABLE_NAMES
        + VERSION_2_TABLE_NAMES
        + VERSION_3_TABLE_NAMES
        + VERSION_4_TABLE_NAMES
    )
    assert names(VERSION_4_TABLES) == VERSION_4_TABLE_NAMES


def test_version_5_adds_remote_tokens_after_every_earlier_table() -> None:
    assert names(SCHEMA_TABLES) == (
        VERSION_1_TABLE_NAMES
        + VERSION_2_TABLE_NAMES
        + VERSION_3_TABLE_NAMES
        + VERSION_4_TABLE_NAMES
        + VERSION_5_TABLE_NAMES
    )
    assert names(VERSION_5_TABLES) == VERSION_5_TABLE_NAMES


def test_only_the_version_3_tables_backfill() -> None:
    assert tuple(table.name for table in SCHEMA_TABLES if table.backfill is not None) == (
        VERSION_3_TABLE_NAMES
    )


def test_every_table_is_created_only_if_it_does_not_exist() -> None:
    for table in (*RUN_PROGRESS_TABLES, *VERSION_3_TABLES, *VERSION_4_TABLES, *VERSION_5_TABLES):
        for statement in table.statements:
            assert "IF NOT EXISTS" in statement, table.name


# The version 2 tables, on either database


JOURNAL_INSERT = """
    INSERT INTO run_journal (
        run_id, position, workflow_id, invocation_id, event_type, recorded_at, payload
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

LEASE_INSERT = """
    INSERT INTO run_leases (run_id, holder, acquired_at, expires_at) VALUES (?, ?, ?, ?)
"""

CHILD_INSERT = """
    INSERT INTO run_children (
        child_run_id, child_workflow_id, child_invocation_id, parent_run_id,
        parent_step_id, parent_attempt, root_run_id, depth, recorded_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def test_a_runs_journal_is_numbered_once_per_position(
    database: Database,
) -> None:
    database.initialize(RUN_PROGRESS_TABLES)

    execute(database, JOURNAL_INSERT, (RUN_ID, 1, WORKFLOW_ID, None, "run.started", NOW, "{}"))
    execute(database, JOURNAL_INSERT, (RUN_ID, 2, WORKFLOW_ID, None, "attempt.started", NOW, "{}"))

    with pytest.raises(IntegrityError):
        execute(database, JOURNAL_INSERT, (RUN_ID, 2, WORKFLOW_ID, None, "layer", NOW, "{}"))

    with database.transaction() as session:
        rows = session.fetchall(
            "SELECT position, event_type, invocation_id FROM run_journal "
            "WHERE run_id = ? ORDER BY position",
            (RUN_ID,),
        )

    assert rows == [(1, "run.started", None), (2, "attempt.started", None)]


def test_a_run_holds_one_lease(
    database: Database,
) -> None:
    database.initialize(RUN_PROGRESS_TABLES)

    execute(database, LEASE_INSERT, (RUN_ID, "holder-1", NOW, NOW))

    with pytest.raises(IntegrityError):
        execute(database, LEASE_INSERT, (RUN_ID, "holder-2", NOW, NOW))


def test_a_child_run_is_indexed_under_one_parent(
    database: Database,
) -> None:
    database.initialize(RUN_PROGRESS_TABLES)

    child = ("c-1", WORKFLOW_ID, None, RUN_ID, "step-1", 1, RUN_ID, 1, NOW)

    execute(database, CHILD_INSERT, child)

    with pytest.raises(IntegrityError):
        execute(database, CHILD_INSERT, child)

    with database.transaction() as session:
        rows = session.fetchall(
            "SELECT child_run_id, parent_attempt, depth FROM run_children WHERE parent_run_id = ?",
            (RUN_ID,),
        )

    assert rows == [("c-1", 1, 1)]


# Upgrading an SQLite file


def test_an_sqlite_file_of_version_1_gains_the_new_tables_when_they_are_prepared(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "azathoth.db")
    database.initialize(VERSION_1_TABLES)

    assert not has_table(database, "run_journal")

    database.prepare(RUN_PROGRESS_TABLES)

    assert all(has_table(database, name) for name in VERSION_2_TABLE_NAMES)


# Upgrading a PostgreSQL database


def test_a_fresh_postgresql_database_is_created_at_version_5(
    postgres_database: PostgresDatabase,
) -> None:
    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.CREATED
    assert recorded_version(postgres_database) == 5
    assert all(
        has_table(postgres_database, name)
        for name in (
            VERSION_2_TABLE_NAMES
            + VERSION_3_TABLE_NAMES
            + VERSION_4_TABLE_NAMES
            + VERSION_5_TABLE_NAMES
        )
    )


def test_a_version_1_database_is_refused_until_initialized(
    postgres_url: str,
) -> None:
    writer = PostgresDatabase(postgres_url)
    reader = PostgresDatabase(postgres_url)

    try:
        initialize_version_1(writer)

        with pytest.raises(DatabaseSchemaOutdatedError) as error:
            reader.prepare(SCHEMA_TABLES)

        assert "has schema version 1, but this Azathoth uses version 5; run azathoth init" in str(
            error.value
        )
        assert not has_table(writer, "run_journal")
    finally:
        writer.close()
        reader.close()


def test_initializing_a_version_1_database_upgrades_it_and_keeps_its_rows(
    postgres_url: str,
) -> None:
    writer = PostgresDatabase(postgres_url)
    reader = PostgresDatabase(postgres_url)

    try:
        initialize_version_1(writer)
        execute(
            writer,
            "INSERT INTO workflow_runs (run_id, workflow_id, payload) VALUES (?, ?, ?)",
            (RUN_ID, WORKFLOW_ID, '{"kept": true}'),
        )

        assert writer.initialize(SCHEMA_TABLES) is InitializationOutcome.UPGRADED
        assert recorded_version(writer) == 5
        assert all(has_table(writer, name) for name in VERSION_2_TABLE_NAMES)
        assert all(has_table(writer, name) for name in VERSION_3_TABLE_NAMES)
        assert all(has_table(writer, name) for name in VERSION_4_TABLE_NAMES)
        assert all(has_table(writer, name) for name in VERSION_5_TABLE_NAMES)

        reader.prepare(SCHEMA_TABLES)

        with reader.transaction() as session:
            assert session.fetchall("SELECT run_id, payload FROM workflow_runs") == [
                (RUN_ID, '{"kept": true}')
            ]
    finally:
        writer.close()
        reader.close()


def test_initializing_an_upgraded_database_again_finds_it_current(
    postgres_database: PostgresDatabase,
) -> None:
    initialize_version_1(postgres_database)

    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.UPGRADED
    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.CURRENT


def test_a_newer_schema_is_never_upgraded_over(
    postgres_database: PostgresDatabase,
) -> None:
    initialize_version_1(postgres_database)
    record_version(postgres_database, SCHEMA_VERSION + 1)

    with pytest.raises(DatabaseSchemaTooNewError, match="upgrade Azathoth"):
        postgres_database.initialize(SCHEMA_TABLES)

    assert recorded_version(postgres_database) == SCHEMA_VERSION + 1
    assert not has_table(postgres_database, "run_journal")


def test_initializing_a_version_2_database_records_the_lineage_it_already_holds(
    postgres_database: PostgresDatabase,
) -> None:
    initialize_version_2(postgres_database)

    digest = "a" * 64

    execute(
        postgres_database,
        "INSERT INTO workflow_specification_revisions "
        "(workflow_id, number, content_digest, payload) VALUES (?, ?, ?, ?)",
        (WORKFLOW_ID, 1, digest, "{}"),
    )
    execute(
        postgres_database,
        "INSERT INTO model_portfolio_entries (identifier, provider, model, payload) "
        "VALUES (?, ?, ?, ?)",
        (
            "openrouter/example/frontier",
            "openrouter",
            "example/frontier",
            '{"provider":"openrouter","model":"example/frontier"}',
        ),
    )

    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.UPGRADED
    assert recorded_version(postgres_database) == 5

    lineage = Lineage(kind=RevisionKind.WORKFLOW, id=UUID(WORKFLOW_ID))

    with postgres_database.transaction() as session:
        assert lineage_records(session, lineage) == (
            LineageRecord(
                lineage=lineage,
                number=1,
                revision_digest=revision_digest(lineage, content_digest=digest, parent_digest=None),
                parent_digest=None,
            ),
        )
        assert session.fetchall(
            "SELECT identifier, author_name, added_at FROM model_portfolio_provenance"
        ) == [("openrouter/example/frontier", None, None)]


def test_initializing_a_version_3_database_adds_the_policy_declarations(
    postgres_database: PostgresDatabase,
) -> None:
    initialize_version_3(postgres_database)

    assert not has_table(postgres_database, "model_portfolio_policy_declarations")
    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.UPGRADED
    assert recorded_version(postgres_database) == 5
    assert has_table(postgres_database, "model_portfolio_policy_declarations")


def test_initializing_a_version_4_database_adds_the_remote_tokens(
    postgres_database: PostgresDatabase,
) -> None:
    initialize_version_4(postgres_database)

    assert not has_table(postgres_database, "remote_tokens")
    assert postgres_database.initialize(SCHEMA_TABLES) is InitializationOutcome.UPGRADED
    assert recorded_version(postgres_database) == 5
    assert has_table(postgres_database, "remote_tokens")
