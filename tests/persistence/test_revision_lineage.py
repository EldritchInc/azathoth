"""Tests of revision lineage and portfolio provenance on either database (ADR 0122)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.evaluation import BENCHMARK_TABLES, BenchmarkDatasetRevision, SqlBenchmarkRepository
from azathoth.persistence import Database, IntegrityError, SQLiteDatabase
from azathoth.providers import (
    MODEL_PORTFOLIO_POLICY_TABLES,
    MODEL_PORTFOLIO_PROVENANCE_TABLES,
    MODEL_PORTFOLIO_TABLES,
    ModelPortfolioEntry,
    PortfolioProvenance,
    SQLiteModelPortfolioRepository,
    SqlModelPortfolioRepository,
)
from azathoth.revisions import (
    REVISION_LINEAGE_TABLES,
    TOOL_REVISION_TABLE,
    WORKFLOW_REVISION_TABLE,
    Author,
    Lineage,
    LineageRecord,
    RevisionKind,
    backfill_lineage,
    content_digest,
    lineage_record,
    lineage_records,
    record_lineage,
    revision_by_digest,
    revision_digest,
    tables_with_lineage,
)
from azathoth.tools import TOOL_TABLES, SqlToolRepository, ToolDocument, ToolDocumentRevision
from azathoth.workflows import (
    WORKFLOW_SPECIFICATION_TABLES,
    SQLiteWorkflowRepository,
    SqlWorkflowRepository,
    WorkflowSpecificationRevision,
)
from tests.cli.test_benchmark_import import BENCHMARK_ID, create_dataset
from tests.cli.test_tool_import import TOOL_ID, create_document
from tests.evaluation.test_benchmark_revision_repository import create_changed_dataset
from tests.tools.test_tool_revision_repository import create_second_version_document
from tests.workflows.test_repository import WORKFLOW_ID, create_workflow
from tests.workflows.test_workflow_revision_repository import (
    create_changed_workflow,
    create_legacy_database,
)

OTHER_WORKFLOW_ID = UUID("e1000000-0000-4000-8000-0000000000ff")

WORKFLOW = Lineage(
    kind=RevisionKind.WORKFLOW,
    id=WORKFLOW_ID,
)

BENCHMARK = Lineage(
    kind=RevisionKind.BENCHMARK,
    id=BENCHMARK_ID,
)

AUTHOR = Author(
    name="Eris Discordia",
    email="eris@example.com",
)


def tool_lineage(
    version: str,
) -> Lineage:
    return Lineage(
        kind=RevisionKind.TOOL,
        id=TOOL_ID,
        version=version,
    )


def changed_tool_document() -> ToolDocument:
    document = create_document()

    return document.model_copy(
        update={
            "definition": document.definition.model_copy(
                update={
                    "description": "Changed tool.",
                },
            ),
        },
    )


def chain(
    lineage: Lineage,
    *content_digests: str,
) -> tuple[LineageRecord, ...]:
    """Return the lineage records a linear history of these contents has."""

    records: list[LineageRecord] = []
    parent: str | None = None

    for number, digest in enumerate(content_digests, start=1):
        digest_of_revision = revision_digest(
            lineage,
            content_digest=digest,
            parent_digest=parent,
        )

        records.append(
            LineageRecord(
                lineage=lineage,
                number=number,
                revision_digest=digest_of_revision,
                parent_digest=parent,
            )
        )

        parent = digest_of_revision

    return tuple(records)


def records(
    database: Database,
    lineage: Lineage,
) -> tuple[LineageRecord, ...]:
    with database.transaction() as session:
        return lineage_records(session, lineage)


def workflows(
    database: Database,
) -> SqlWorkflowRepository:
    database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    return SqlWorkflowRepository(database)


def insert_workflow_revision(
    database: Database,
    revision: WorkflowSpecificationRevision,
) -> None:
    """Write one revision row as an Azathoth from before lineage did."""

    with database.transaction() as session:
        session.execute(
            """
            INSERT INTO workflow_specification_revisions (
                workflow_id, number, content_digest, payload
            ) VALUES (?, ?, ?, ?)
            """,
            (
                str(revision.workflow_id),
                revision.number,
                revision.content_digest,
                revision.model_dump_json(),
            ),
        )


def insert_tool_revision(
    database: Database,
    revision: ToolDocumentRevision,
) -> None:
    """Write one tool revision row as an Azathoth from before lineage did."""

    with database.transaction() as session:
        session.execute(
            """
            INSERT INTO tool_document_revisions (
                tool_id, tool_version, number, content_digest, payload
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(revision.tool_id),
                revision.tool_version,
                revision.number,
                revision.content_digest,
                revision.model_dump_json(),
            ),
        )


def insert_portfolio_entry(
    database: Database,
    entry: ModelPortfolioEntry,
) -> None:
    """Write one portfolio entry as an Azathoth from before provenance did."""

    with database.transaction() as session:
        session.execute(
            """
            INSERT INTO model_portfolio_entries (identifier, provider, model, payload)
            VALUES (?, ?, ?, ?)
            """,
            (entry.identifier, entry.provider, entry.model, entry.model_dump_json()),
        )


# Recording lineage as revisions are appended


def test_each_workflow_revision_records_its_parent(
    database: Database,
) -> None:
    repository = workflows(database)

    first = repository.save(create_workflow())
    second = repository.save(create_changed_workflow())
    third = repository.save(create_workflow())

    assert records(database, WORKFLOW) == chain(
        WORKFLOW,
        first.content_digest,
        second.content_digest,
        third.content_digest,
    )


def test_a_revert_records_a_new_revision_digest(
    database: Database,
) -> None:
    repository = workflows(database)

    repository.save(create_workflow())
    repository.save(create_changed_workflow())
    repository.save(create_workflow())

    first, _, third = records(database, WORKFLOW)

    assert third.revision_digest != first.revision_digest


def test_each_tool_version_records_a_lineage_of_its_own(
    database: Database,
) -> None:
    database.initialize(tables_with_lineage(TOOL_TABLES))
    repository = SqlToolRepository(database)

    first = repository.save_document(create_document())
    other_version = repository.save_document(create_second_version_document())
    second = repository.save_document(changed_tool_document())

    assert records(database, tool_lineage("1.0.0")) == chain(
        tool_lineage("1.0.0"),
        first.content_digest,
        second.content_digest,
    )
    assert records(database, tool_lineage("2.0.0")) == chain(
        tool_lineage("2.0.0"),
        other_version.content_digest,
    )
    assert {record.lineage.version for record in records(database, tool_lineage("2.0.0"))} == {
        "2.0.0"
    }


def test_each_benchmark_revision_records_its_parent(
    database: Database,
) -> None:
    database.initialize(tables_with_lineage(BENCHMARK_TABLES))
    repository = SqlBenchmarkRepository(database)

    first = repository.save(create_dataset())
    second = repository.save(create_changed_dataset())

    assert isinstance(first, BenchmarkDatasetRevision)
    assert records(database, BENCHMARK) == chain(
        BENCHMARK,
        first.content_digest,
        second.content_digest,
    )


def test_a_revision_is_found_by_its_revision_digest(
    database: Database,
) -> None:
    repository = workflows(database)

    repository.save(create_workflow())
    repository.save(create_changed_workflow())

    _, second = records(database, WORKFLOW)

    with database.transaction() as session:
        assert revision_by_digest(session, RevisionKind.WORKFLOW, second.revision_digest) == second
        assert revision_by_digest(session, RevisionKind.BENCHMARK, second.revision_digest) is None
        assert revision_by_digest(session, RevisionKind.WORKFLOW, "f" * 64) is None


def test_one_numbered_revision_is_read_back(
    database: Database,
) -> None:
    repository = workflows(database)

    repository.save(create_workflow())

    (first,) = records(database, WORKFLOW)

    with database.transaction() as session:
        assert lineage_record(session, WORKFLOW, 1) == first
        assert lineage_record(session, WORKFLOW, 2) is None


def test_an_author_is_recorded_and_read_back(
    database: Database,
) -> None:
    database.initialize(REVISION_LINEAGE_TABLES)

    with database.transaction() as session:
        first = record_lineage(session, WORKFLOW, number=1, content_digest="a" * 64, author=AUTHOR)
        second = record_lineage(
            session,
            WORKFLOW,
            number=2,
            content_digest="b" * 64,
            author=Author(name="oren"),
        )

    assert records(database, WORKFLOW) == (first, second)
    assert first.author == AUTHOR
    assert second.author == Author(name="oren")


def test_a_revision_whose_predecessor_has_no_lineage_is_refused(
    database: Database,
) -> None:
    database.initialize(REVISION_LINEAGE_TABLES)

    with pytest.raises(LookupError) as caught, database.transaction() as session:
        record_lineage(session, WORKFLOW, number=2, content_digest="a" * 64)

    assert str(caught.value) == f"Revision 1 of workflow {WORKFLOW_ID} has no lineage record."


def test_a_revision_is_recorded_once(
    database: Database,
) -> None:
    database.initialize(REVISION_LINEAGE_TABLES)

    with database.transaction() as session:
        record_lineage(session, WORKFLOW, number=1, content_digest="a" * 64)

    with pytest.raises(IntegrityError), database.transaction() as session:
        record_lineage(session, WORKFLOW, number=1, content_digest="b" * 64)


def test_the_same_revision_digest_is_kept_once_per_kind(
    database: Database,
) -> None:
    database.initialize(REVISION_LINEAGE_TABLES)

    with database.transaction() as session:
        record_lineage(session, WORKFLOW, number=1, content_digest="a" * 64)

    with pytest.raises(IntegrityError), database.transaction() as session:
        session.execute(
            """
            INSERT INTO revision_lineage (
                kind, lineage_id, lineage_version, number, revision_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "workflow",
                str(OTHER_WORKFLOW_ID),
                "",
                1,
                revision_digest(WORKFLOW, content_digest="a" * 64, parent_digest=None),
            ),
        )


# Backfilling revisions imported before lineage was recorded


def test_initializing_records_the_lineage_of_earlier_revisions(
    database: Database,
) -> None:
    database.initialize(WORKFLOW_SPECIFICATION_TABLES)

    first = WorkflowSpecificationRevision.create(create_workflow(), number=1)
    second = WorkflowSpecificationRevision.create(create_changed_workflow(), number=2)

    insert_workflow_revision(database, first)
    insert_workflow_revision(database, second)

    database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    assert records(database, WORKFLOW) == chain(
        WORKFLOW,
        first.content_digest,
        second.content_digest,
    )


def test_backfilling_again_records_nothing(
    database: Database,
) -> None:
    database.initialize(WORKFLOW_SPECIFICATION_TABLES)
    insert_workflow_revision(
        database,
        WorkflowSpecificationRevision.create(create_workflow(), number=1),
    )
    database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    before = records(database, WORKFLOW)

    with database.transaction() as session:
        assert backfill_lineage(session, WORKFLOW_REVISION_TABLE) == 0

    database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))

    assert records(database, WORKFLOW) == before


def test_a_backfill_continues_a_lineage_from_its_last_record(
    database: Database,
) -> None:
    database.initialize(tables_with_lineage(TOOL_TABLES))

    first = ToolDocumentRevision.create(create_document(), number=1)
    second = ToolDocumentRevision.create(changed_tool_document(), number=2)

    insert_tool_revision(database, first)

    with database.transaction() as session:
        assert backfill_lineage(session, TOOL_REVISION_TABLE) == 1

    insert_tool_revision(database, second)

    with database.transaction() as session:
        assert backfill_lineage(session, TOOL_REVISION_TABLE) == 1

    assert records(database, tool_lineage("1.0.0")) == chain(
        tool_lineage("1.0.0"),
        first.content_digest,
        second.content_digest,
    )


def test_a_backfill_reads_only_the_tables_being_initialized(
    database: Database,
) -> None:
    database.initialize(WORKFLOW_SPECIFICATION_TABLES)
    insert_workflow_revision(
        database,
        WorkflowSpecificationRevision.create(create_workflow(), number=1),
    )

    database.initialize(REVISION_LINEAGE_TABLES)

    assert records(database, WORKFLOW) == ()


def test_a_backfill_refuses_a_revision_whose_predecessor_is_missing(
    database: Database,
) -> None:
    database.initialize(WORKFLOW_SPECIFICATION_TABLES)
    insert_workflow_revision(
        database,
        WorkflowSpecificationRevision.create(create_workflow(), number=2),
    )

    with pytest.raises(LookupError, match=f"Revision 1 of workflow {WORKFLOW_ID} has no"):
        database.initialize(tables_with_lineage(WORKFLOW_SPECIFICATION_TABLES))


def test_an_sqlite_file_from_before_lineage_gains_it_when_opened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"
    sqlite = SQLiteDatabase(path)
    sqlite.initialize(WORKFLOW_SPECIFICATION_TABLES)

    first = WorkflowSpecificationRevision.create(create_workflow(), number=1)

    insert_workflow_revision(sqlite, first)

    repository = SQLiteWorkflowRepository(path)
    second = repository.save(create_changed_workflow())

    assert records(sqlite, WORKFLOW) == chain(
        WORKFLOW,
        first.content_digest,
        second.content_digest,
    )


def test_an_sqlite_file_from_before_revisions_gains_their_lineage_when_opened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"

    create_legacy_database(path, (create_workflow(),))

    repository = SQLiteWorkflowRepository(path)

    (revision,) = repository.revisions(WORKFLOW_ID)

    assert records(SQLiteDatabase(path), WORKFLOW) == chain(WORKFLOW, revision.content_digest)


# Portfolio provenance


def portfolio(
    database: Database,
) -> SqlModelPortfolioRepository:
    database.initialize(
        (
            *MODEL_PORTFOLIO_TABLES,
            *MODEL_PORTFOLIO_PROVENANCE_TABLES,
            *MODEL_PORTFOLIO_POLICY_TABLES,
        )
    )

    return SqlModelPortfolioRepository(database)


ENTRY = ModelPortfolioEntry(
    provider="openrouter",
    model="example/frontier",
)

OTHER_ENTRY = ModelPortfolioEntry(
    provider="openrouter",
    model="example/other",
)


def test_adding_an_entry_records_its_digest_and_when(
    database: Database,
) -> None:
    repository = portfolio(database)

    before = datetime.now(UTC)
    repository.save(ENTRY)
    after = datetime.now(UTC)

    provenance = repository.provenance(ENTRY.identifier)

    assert provenance is not None
    assert provenance.identifier == ENTRY.identifier
    assert provenance.content_digest == content_digest(ENTRY)
    assert provenance.author is None
    assert provenance.added_at is not None
    assert before <= provenance.added_at <= after


def test_removing_an_entry_removes_its_provenance(
    database: Database,
) -> None:
    repository = portfolio(database)

    repository.save(ENTRY)
    repository.save(OTHER_ENTRY)
    repository.delete(ENTRY.identifier)

    assert repository.provenance(ENTRY.identifier) is None
    assert repository.provenance(OTHER_ENTRY.identifier) is not None


def test_a_refused_duplicate_keeps_the_first_provenance(
    database: Database,
) -> None:
    repository = portfolio(database)

    repository.save(ENTRY)
    first = repository.provenance(ENTRY.identifier)

    with pytest.raises(ValueError, match="already exists"):
        repository.save(ENTRY)

    assert repository.provenance(ENTRY.identifier) == first


def test_provenance_backfills_only_when_the_portfolio_is_initialized_with_it(
    database: Database,
) -> None:
    database.initialize(MODEL_PORTFOLIO_PROVENANCE_TABLES)

    with database.transaction() as session:
        assert session.fetchall("SELECT identifier FROM model_portfolio_provenance") == []


def test_an_entry_outside_the_portfolio_has_no_provenance(
    database: Database,
) -> None:
    assert portfolio(database).provenance("openrouter/missing") is None


def test_entries_added_before_provenance_gain_their_digest_without_author_or_time(
    database: Database,
) -> None:
    database.initialize(MODEL_PORTFOLIO_TABLES)
    insert_portfolio_entry(database, ENTRY)

    repository = portfolio(database)

    assert repository.provenance(ENTRY.identifier) == PortfolioProvenance(
        identifier=ENTRY.identifier,
        content_digest=content_digest(ENTRY),
    )


def test_an_sqlite_portfolio_from_before_provenance_gains_it_when_opened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "azathoth.db"

    SQLiteDatabase(path).initialize(MODEL_PORTFOLIO_TABLES)

    connection = sqlite3.connect(path)

    try:
        connection.execute(
            """
            INSERT INTO model_portfolio_entries (identifier, provider, model, payload)
            VALUES (?, ?, ?, ?)
            """,
            (ENTRY.identifier, ENTRY.provider, ENTRY.model, ENTRY.model_dump_json()),
        )
        connection.commit()
    finally:
        connection.close()

    provenance = SQLiteModelPortfolioRepository(path).provenance(ENTRY.identifier)

    assert provenance is not None
    assert provenance.content_digest == content_digest(ENTRY)
    assert provenance.added_at is None


def test_a_revision_recorded_with_no_parent_is_a_root_whatever_its_number(
    database: Database,
) -> None:
    database.initialize(REVISION_LINEAGE_TABLES)

    with database.transaction() as session:
        first = record_lineage(session, WORKFLOW, number=1, content_digest="a" * 64)
        root = record_lineage(session, WORKFLOW, number=2, content_digest="b" * 64, parent=None)
        child = record_lineage(session, WORKFLOW, number=3, content_digest="c" * 64, parent=first)

    assert root.parent_digest is None
    assert child.parent_digest == first.revision_digest
