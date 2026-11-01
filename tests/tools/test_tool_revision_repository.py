"""Tests for revisioned tool documents in tool repositories."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.revisions import content_digest
from azathoth.tools import (
    InMemoryToolRepository,
    SQLiteToolRepository,
    ToolDocument,
    ToolDocumentRevision,
    ToolRepository,
    earliest_identical_tool_revision,
    require_tool_repository,
)
from tests.cli.test_tool_import import (
    OTHER_TOOL_ID,
    TOOL_ID,
    create_changed_document,
    create_definition,
    create_document,
    create_implementation,
    create_renamed_document,
    create_test_case,
)


def create_repositories(
    tmp_path: Path,
) -> tuple[ToolRepository, ...]:
    """Return one empty repository of each implementation."""

    return (
        require_tool_repository(InMemoryToolRepository()),
        require_tool_repository(SQLiteToolRepository(tmp_path / "azathoth.db")),
    )


def create_second_version_document() -> ToolDocument:
    """Create version 2.0.0 of the tool, sharing its test case."""

    return ToolDocument(
        definition=create_definition().model_copy(
            update={
                "version": "2.0.0",
            },
        ),
        implementations=(
            create_implementation().model_copy(
                update={
                    "id": OTHER_TOOL_ID,
                    "tool_version": "2.0.0",
                },
            ),
        ),
        test_cases=(create_test_case(),),
    )


def test_revisions_record_their_tool_version_and_digest() -> None:
    revision = ToolDocumentRevision.create(
        create_document(),
        number=1,
    )

    assert revision.tool_id == TOOL_ID
    assert revision.tool_version == "1.0.0"
    assert revision.reference == f"{TOOL_ID}@1.0.0"
    assert revision.content_digest == content_digest(create_document())


def test_revision_documents_must_define_their_tool_version() -> None:
    with pytest.raises(
        ValidationError,
        match="Tool revision document must define its tool version.",
    ):
        ToolDocumentRevision(
            tool_id=TOOL_ID,
            tool_version="9.9.9",
            number=1,
            document=create_document(),
            content_digest=content_digest(create_document()),
        )


def test_earliest_identical_revision_is_per_tool_version() -> None:
    first = ToolDocumentRevision.create(create_document(), number=1)
    changed = ToolDocumentRevision.create(create_changed_document(), number=2)
    reverted = ToolDocumentRevision.create(create_document(), number=3)
    other_version = ToolDocumentRevision.create(create_second_version_document(), number=1)

    history = (first, changed, reverted, other_version)

    assert earliest_identical_tool_revision(history, reverted) == first
    assert earliest_identical_tool_revision(history, changed) is None
    assert earliest_identical_tool_revision(history, other_version) is None


def test_documents_append_numbered_revisions_per_version(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save_document(create_document())
        second = repository.save_document(create_changed_document())
        other = repository.save_document(create_second_version_document())

        assert (first.number, second.number, other.number) == (1, 2, 1)
        assert repository.document_revisions(TOOL_ID) == (first, second, other)


def test_revisions_are_found_by_number_and_latest(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        first = repository.save_document(create_document())
        second = repository.save_document(create_changed_document())

        assert repository.document_revision(TOOL_ID, "1.0.0", 1) == first
        assert repository.document_revision(TOOL_ID, "1.0.0", 3) is None
        assert repository.latest_document_revision(TOOL_ID, "1.0.0") == second
        assert repository.latest_document_revision(TOOL_ID, "2.0.0") is None


def test_the_latest_revision_defines_current_artifacts(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_document(create_document())
        repository.save_document(create_changed_document())

        assert repository.definitions() == (create_definition(),)
        assert repository.implementations() == create_changed_document().implementations
        assert repository.test_cases() == ()

        repository.save_document(create_document())

        assert repository.implementations() == (create_implementation(),)
        assert repository.test_cases() == (create_test_case(),)


def test_test_cases_shared_with_another_version_stay_current(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_document(create_document())
        repository.save_document(create_second_version_document())
        repository.save_document(create_changed_document())

        assert repository.test_cases() == (create_test_case(),)
        assert len(repository.implementations()) == 2


def test_conflicting_documents_change_nothing(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_document(create_document())

        conflicting = ToolDocument(
            definition=create_definition().model_copy(
                update={
                    "version": "2.0.0",
                },
            ),
            implementations=(
                create_implementation().model_copy(
                    update={
                        "tool_version": "2.0.0",
                    },
                ),
            ),
        )

        with pytest.raises(ValueError, match="belongs to tool"):
            repository.save_document(conflicting)

        assert repository.definitions() == (create_definition(),)
        assert repository.implementations() == (create_implementation(),)
        assert repository.latest_document_revision(TOOL_ID, "2.0.0") is None
        assert len(repository.document_revisions(TOOL_ID)) == 1


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
def test_a_document_cannot_rename_a_saved_tool(
    tmp_path: Path,
    version: str,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_document(create_document())

        with pytest.raises(ValueError) as error:
            repository.save_document(create_renamed_document(version))

        assert str(error.value) == (
            f"Tool {TOOL_ID} is named 'word_count'; a document cannot rename it to 'line_count'."
        )
        assert repository.definitions() == (create_definition(),)
        assert repository.implementations() == (create_implementation(),)
        assert len(repository.document_revisions(TOOL_ID)) == 1


def test_a_document_cannot_rename_a_tool_saved_artifact_by_artifact(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_definition(create_definition())

        with pytest.raises(ValueError, match="cannot rename it to 'line_count'"):
            repository.save_document(create_renamed_document("1.0.0"))

        assert repository.definitions() == (create_definition(),)


def test_a_new_version_keeping_the_name_is_still_saved(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_document(create_document())

        revision = repository.save_document(create_second_version_document())

        assert revision.number == 1
        assert revision.document.definition.version == "2.0.0"


def test_versions_saved_artifact_by_artifact_become_first_revisions(
    tmp_path: Path,
) -> None:
    for repository in create_repositories(tmp_path):
        repository.save_definition(create_definition())
        repository.save_implementation(create_implementation())
        repository.save_test_case(create_test_case())

        revision = repository.save_document(create_changed_document())

        first = repository.document_revision(TOOL_ID, "1.0.0", 1)

        assert revision.number == 2
        assert first is not None
        assert first.imported_at is None
        assert first.document == create_document()


def test_sqlite_records_unrevisioned_versions_when_opened(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    repository = SQLiteToolRepository(database)

    repository.save_definition(create_definition())
    repository.save_implementation(create_implementation())

    reopened = SQLiteToolRepository(database)

    (revision,) = reopened.document_revisions(TOOL_ID)

    assert revision.number == 1
    assert revision.imported_at is None
    assert revision.document.implementations == (create_implementation(),)


def test_sqlite_revisions_survive_reopening(
    tmp_path: Path,
) -> None:
    database = tmp_path / "azathoth.db"

    saved = (
        SQLiteToolRepository(database).save_document(create_document()),
        SQLiteToolRepository(database).save_document(create_changed_document()),
    )

    reopened = SQLiteToolRepository(database)

    assert reopened.document_revisions(TOOL_ID) == saved
    assert reopened.implementations() == create_changed_document().implementations
