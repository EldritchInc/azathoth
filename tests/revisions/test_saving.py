"""Tests for choosing the revision a save builds on, and the record it makes (ADR 0122)."""

from uuid import UUID

import pytest

from azathoth.revisions import (
    PREVIOUS,
    Author,
    BaseRevisionError,
    Lineage,
    LineageRecord,
    RevisionKind,
    SavedRevision,
    base_record,
    child_record,
    revision_digest,
)

WORKFLOW = Lineage(
    kind=RevisionKind.WORKFLOW,
    id=UUID("e1000000-0000-4000-8000-000000000001"),
)

OTHER = Lineage(
    kind=RevisionKind.WORKFLOW,
    id=UUID("e1000000-0000-4000-8000-000000000002"),
)

AUTHOR = Author(
    name="Eris",
)


def first() -> LineageRecord:
    return child_record(WORKFLOW, number=1, content_digest="a" * 64, parent=None)


def second() -> LineageRecord:
    return child_record(WORKFLOW, number=2, content_digest="b" * 64, parent=first())


def test_the_default_parent_is_named_previous() -> None:
    assert PREVIOUS == "previous"


def test_a_first_record_has_no_parent() -> None:
    assert first() == LineageRecord(
        lineage=WORKFLOW,
        number=1,
        revision_digest=revision_digest(WORKFLOW, content_digest="a" * 64, parent_digest=None),
        parent_digest=None,
    )


def test_a_child_record_names_its_parent_and_author() -> None:
    child = child_record(
        WORKFLOW,
        number=2,
        content_digest="b" * 64,
        parent=first(),
        author=AUTHOR,
    )

    assert child.parent_digest == first().revision_digest
    assert child.revision_digest == revision_digest(
        WORKFLOW,
        content_digest="b" * 64,
        parent_digest=first().revision_digest,
    )
    assert child.author == AUTHOR


def test_a_child_of_another_lineages_revision_is_refused() -> None:
    with pytest.raises(BaseRevisionError) as caught:
        child_record(OTHER, number=2, content_digest="b" * 64, parent=first())

    assert str(caught.value) == (
        f"Revision {first().revision_digest} is not a revision of workflow {OTHER.id}."
    )


def test_a_base_revision_error_is_a_value_error() -> None:
    assert issubclass(BaseRevisionError, ValueError)


def test_without_a_digest_a_save_builds_on_the_latest() -> None:
    assert base_record((second(), first()), WORKFLOW, None) == second()


def test_a_lineages_first_save_builds_on_nothing() -> None:
    assert base_record((), WORKFLOW, None) is None


def test_a_digest_names_the_revision_a_save_builds_on() -> None:
    assert base_record((first(), second()), WORKFLOW, first().revision_digest) == first()


def test_a_digest_no_revision_has_is_refused() -> None:
    with pytest.raises(BaseRevisionError) as caught:
        base_record((first(), second()), WORKFLOW, "f" * 64)

    assert str(caught.value) == f"Revision {'f' * 64} is not a revision of workflow {WORKFLOW.id}."


def test_a_saved_revision_says_whether_it_is_new() -> None:
    saved = SavedRevision(revision="revision", lineage=first(), created=False)

    assert (saved.revision, saved.lineage, saved.created) == ("revision", first(), False)
