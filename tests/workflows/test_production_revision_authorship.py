"""Tests that production revisions record who made them, and what they restore (ADR 0128)."""

from pathlib import Path
from uuid import UUID

from azathoth.revisions import Author
from azathoth.workflows import (
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    SQLiteWorkflowProductionRevisionRepository,
    WorkflowProductionRevision,
    promote_workflow_candidate,
)
from tests.workflows.test_promotion import (
    create_candidate,
    create_workflow,
)

AUTHOR = Author(name="Eris Discordia", email="eris@example.com")

EARLIER_REVISION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")


def promote(
    *,
    author: Author | None = None,
) -> WorkflowProductionRevision:
    """Promote the test workflow's candidate into fresh repositories."""

    specification = create_workflow()

    return promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
        author=author,
    )


def test_a_promotion_records_its_author() -> None:
    assert promote(author=AUTHOR).author == AUTHOR


def test_a_promotion_without_an_author_records_none() -> None:
    assert promote().author is None


def test_a_promotion_restores_nothing() -> None:
    assert promote(author=AUTHOR).restores is None


def test_a_revision_saved_before_1_5_reads_back_with_neither() -> None:
    revision = promote()
    payload = revision.model_dump(mode="json")

    del payload["author"]
    del payload["restores"]

    restored = WorkflowProductionRevision.model_validate(payload)

    assert restored.author is None
    assert restored.restores is None
    assert restored.state == revision.state


def test_author_and_restores_survive_the_database(
    tmp_path: Path,
) -> None:
    revision = promote(author=AUTHOR).model_copy(update={"restores": EARLIER_REVISION_ID})
    repository = SQLiteWorkflowProductionRevisionRepository(tmp_path / "azathoth.db")

    repository.save(revision)

    saved = repository.get(revision.id)

    assert saved is not None
    assert saved.author == AUTHOR
    assert saved.restores == EARLIER_REVISION_ID
