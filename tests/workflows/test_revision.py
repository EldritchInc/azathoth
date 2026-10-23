"""Tests for immutable workflow specification revisions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from azathoth.revisions import content_digest
from azathoth.workflows import (
    WorkflowSpecification,
    WorkflowSpecificationRevision,
    earliest_identical_revision,
)
from tests.workflows.test_repository import (
    SECOND_WORKFLOW_ID,
    WORKFLOW_ID,
    create_workflow,
)

IMPORTED_AT = datetime(
    2026,
    10,
    23,
    13,
    0,
    tzinfo=UTC,
)


def create_revision(
    number: int,
    *,
    specification: WorkflowSpecification | None = None,
) -> WorkflowSpecificationRevision:
    """Create one deterministic revision of the default workflow."""

    return WorkflowSpecificationRevision.create(
        specification if specification is not None else create_workflow(),
        number=number,
        imported_at=IMPORTED_AT,
    )


def test_revision_records_its_workflow_and_number() -> None:
    revision = create_revision(3)

    assert revision.workflow_id == WORKFLOW_ID
    assert revision.number == 3
    assert revision.specification == create_workflow()
    assert revision.imported_at == IMPORTED_AT


def test_revision_digests_the_specification_as_imported() -> None:
    specification = create_workflow()

    assert create_revision(1).content_digest == content_digest(specification)


def test_revisions_of_identical_content_share_a_digest() -> None:
    assert create_revision(1).content_digest == create_revision(2).content_digest


def test_revisions_of_changed_content_differ() -> None:
    renamed = create_workflow(
        name="Renamed workflow",
    )

    assert (
        create_revision(1).content_digest
        != create_revision(
            2,
            specification=renamed,
        ).content_digest
    )


def test_revision_defaults_to_the_current_utc_time() -> None:
    revision = WorkflowSpecificationRevision.create(
        create_workflow(),
        number=1,
    )

    assert revision.imported_at.utcoffset() == UTC.utcoffset(None)


def test_revision_numbers_start_at_one() -> None:
    with pytest.raises(ValidationError):
        create_revision(0)


def test_revision_requires_a_hex_sha256_digest() -> None:
    with pytest.raises(ValidationError):
        WorkflowSpecificationRevision(
            workflow_id=WORKFLOW_ID,
            number=1,
            specification=create_workflow(),
            content_digest="not-a-digest",
        )


def test_revision_specification_must_belong_to_its_workflow() -> None:
    with pytest.raises(
        ValidationError,
        match="Workflow revision specification must belong to its workflow.",
    ):
        WorkflowSpecificationRevision(
            workflow_id=SECOND_WORKFLOW_ID,
            number=1,
            specification=create_workflow(),
            content_digest=content_digest(create_workflow()),
        )


def test_revision_keeps_its_stored_digest_when_decoded() -> None:
    """Stored digests are compared, never recomputed on decode."""

    stored = WorkflowSpecificationRevision(
        workflow_id=WORKFLOW_ID,
        number=1,
        specification=create_workflow(),
        content_digest="0" * 64,
        imported_at=IMPORTED_AT,
    )

    decoded = WorkflowSpecificationRevision.model_validate_json(
        stored.model_dump_json(),
    )

    assert decoded == stored
    assert decoded.content_digest == "0" * 64


def test_revision_round_trips_through_json() -> None:
    revision = create_revision(2)

    assert (
        WorkflowSpecificationRevision.model_validate_json(
            revision.model_dump_json(),
        )
        == revision
    )


def test_earliest_identical_revision_names_the_reverted_revision() -> None:
    original = create_revision(1)

    changed = create_revision(
        2,
        specification=create_workflow(
            name="Changed workflow",
        ),
    )

    reverted = create_revision(3)

    again = create_revision(4)

    history = (
        original,
        changed,
        reverted,
        again,
    )

    assert earliest_identical_revision(history, reverted) == original
    assert earliest_identical_revision(history, again) == original


def test_earliest_identical_revision_ignores_later_and_changed_revisions() -> None:
    original = create_revision(1)

    changed = create_revision(
        2,
        specification=create_workflow(
            name="Changed workflow",
        ),
    )

    reverted = create_revision(3)

    history = (
        original,
        changed,
        reverted,
    )

    assert earliest_identical_revision(history, original) is None
    assert earliest_identical_revision(history, changed) is None


def test_earliest_identical_revision_ignores_other_workflows() -> None:
    other = create_revision(
        1,
        specification=create_workflow(
            workflow_id=SECOND_WORKFLOW_ID,
        ),
    )

    revision = create_revision(2)

    assert earliest_identical_revision((other, revision), revision) is None
