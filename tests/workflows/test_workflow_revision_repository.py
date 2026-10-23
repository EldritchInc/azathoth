"""Tests for revisioned workflow specification repositories."""

import sqlite3
from pathlib import Path

import pytest

from azathoth.revisions import content_digest
from azathoth.workflows import (
    InMemoryWorkflowRepository,
    SQLiteWorkflowRepository,
    WorkflowRepository,
    WorkflowSpecification,
    require_workflow_repository,
)
from tests.workflows.test_repository import (
    SECOND_WORKFLOW_ID,
    WORKFLOW_ID,
    create_workflow,
)


def create_changed_workflow() -> WorkflowSpecification:
    """Create the default workflow with changed content."""

    return create_workflow(
        name="Changed workflow",
    )


def create_repositories(
    tmp_path: Path,
) -> tuple[WorkflowRepository, ...]:
    """Return one empty repository of each implementation."""

    return (
        require_workflow_repository(InMemoryWorkflowRepository()),
        require_workflow_repository(SQLiteWorkflowRepository(tmp_path / "azathoth.db")),
    )


def create_legacy_database(
    database: Path,
    specifications: tuple[WorkflowSpecification, ...],
) -> None:
    """Write a database in the layout used before workflow revisions."""

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            CREATE TABLE workflow_specifications (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            )
            """
        )

        for specification in specifications:
            connection.execute(
                """
                INSERT INTO workflow_specifications (
                    workflow_id,
                    payload
                )
                VALUES (?, ?)
                """,
                (
                    str(specification.metadata.id),
                    specification.model_dump_json(),
                ),
            )

        connection.commit()
    finally:
        connection.close()


def test_saves_append_numbered_revisions(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save(create_workflow())
        second = repository.save(create_changed_workflow())
        third = repository.save(create_workflow())

        assert (first.number, second.number, third.number) == (1, 2, 3)
        assert {first.workflow_id, second.workflow_id, third.workflow_id} == {WORKFLOW_ID}


def test_revision_numbers_are_per_workflow(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save(create_workflow())
        repository.save(create_changed_workflow())

        other = repository.save(
            create_workflow(
                workflow_id=SECOND_WORKFLOW_ID,
            )
        )

        assert other.number == 1


def test_get_returns_the_latest_specification(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save(create_workflow())
        repository.save(create_changed_workflow())

        assert repository.get(WORKFLOW_ID) == create_changed_workflow()


def test_specifications_lists_latest_revisions_in_first_import_order(
    tmp_path: Path,
) -> None:
    second_workflow = create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        name="Second workflow",
    )

    for repository in create_repositories(tmp_path):
        repository.save(create_workflow())
        repository.save(second_workflow)
        repository.save(create_changed_workflow())

        assert repository.specifications() == (
            create_changed_workflow(),
            second_workflow,
        )


def test_revisions_are_returned_oldest_first(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        saved = (
            repository.save(create_workflow()),
            repository.save(create_changed_workflow()),
        )

        assert repository.revisions(WORKFLOW_ID) == saved
        assert repository.revisions(SECOND_WORKFLOW_ID) == ()


def test_revisions_are_found_by_number(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save(create_workflow())
        second = repository.save(create_changed_workflow())

        assert repository.revision(WORKFLOW_ID, 1) == first
        assert repository.revision(WORKFLOW_ID, 2) == second
        assert repository.revision(WORKFLOW_ID, 3) is None
        assert repository.revision(SECOND_WORKFLOW_ID, 1) is None


def test_latest_revision_follows_every_save(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        assert repository.latest_revision(WORKFLOW_ID) is None

        repository.save(create_workflow())
        second = repository.save(create_changed_workflow())

        assert repository.latest_revision(WORKFLOW_ID) == second


def test_revisions_record_content_digests(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save(create_workflow())
        changed = repository.save(create_changed_workflow())
        reverted = repository.save(create_workflow())

        assert first.content_digest == content_digest(create_workflow())
        assert changed.content_digest != first.content_digest
        assert reverted.content_digest == first.content_digest


def test_sqlite_revisions_survive_reopening(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    saved = (
        SQLiteWorkflowRepository(database).save(create_workflow()),
        SQLiteWorkflowRepository(database).save(create_changed_workflow()),
    )

    assert SQLiteWorkflowRepository(database).revisions(WORKFLOW_ID) == saved


def test_sqlite_migrates_legacy_specifications_as_first_revisions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    second_workflow = create_workflow(
        workflow_id=SECOND_WORKFLOW_ID,
        name="Second workflow",
    )

    create_legacy_database(
        database,
        (
            create_workflow(),
            second_workflow,
        ),
    )

    repository = SQLiteWorkflowRepository(database)

    assert repository.specifications() == (
        create_workflow(),
        second_workflow,
    )

    (revision,) = repository.revisions(WORKFLOW_ID)

    assert revision.number == 1
    assert revision.imported_at is None
    assert revision.content_digest == content_digest(create_workflow())


def test_sqlite_migration_runs_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    create_legacy_database(
        database,
        (create_workflow(),),
    )

    SQLiteWorkflowRepository(database).save(create_changed_workflow())

    reopened = SQLiteWorkflowRepository(database)

    assert tuple(revision.number for revision in reopened.revisions(WORKFLOW_ID)) == (1, 2)
    assert reopened.get(WORKFLOW_ID) == create_changed_workflow()


def test_sqlite_migration_keeps_the_legacy_table(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    create_legacy_database(
        database,
        (create_workflow(),),
    )

    SQLiteWorkflowRepository(database).save(create_changed_workflow())

    connection = sqlite3.connect(database)

    try:
        rows = connection.execute(
            "SELECT workflow_id FROM workflow_specifications",
        ).fetchall()
    finally:
        connection.close()

    assert rows == [(str(WORKFLOW_ID),)]


def test_new_databases_create_no_legacy_table(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    SQLiteWorkflowRepository(database).save(create_workflow())

    connection = sqlite3.connect(database)

    try:
        legacy = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'workflow_specifications'
            """
        ).fetchone()
    finally:
        connection.close()

    assert legacy is None


def test_sqlite_rejects_a_corrupted_revision_payload(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteWorkflowRepository(database)

    connection = sqlite3.connect(database)

    try:
        connection.execute(
            """
            INSERT INTO workflow_specification_revisions (
                workflow_id,
                number,
                content_digest,
                payload
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                str(WORKFLOW_ID),
                1,
                "0" * 64,
                b"not text",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        TypeError,
        match="Persisted workflow revision payload was not text.",
    ):
        repository.get(WORKFLOW_ID)
