"""Tests for the lineages revisions belong to and their revision digests."""

import hashlib
import re
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.revisions import (
    CONTENT_DIGEST_PATTERN,
    REVISION_DIGEST_FORMAT,
    Lineage,
    RevisionKind,
    revision_digest,
)

WORKFLOW_ID = UUID("e1000000-0000-4000-8000-000000000001")

TOOL_ID = UUID("c1000000-0000-4000-8000-000000000001")

CONTENT = "a" * 64

OTHER_CONTENT = "b" * 64

PARENT = "c" * 64

PINNED_ROOT = "d2e08ba687ece47634916d456e61d77dee50a2a0176ba606575100caeb5c4c77"

PINNED_CHILD = "bc37cb07b6e61713bb6b62b0d8782b9590ac751457fc6bc40452cda72ff0a3bc"

PINNED_TOOL = "bdd5832d6b69e98a7da7ce06b71efd21452fea8abcbe4b500a0d76551fba4cfe"


def workflow() -> Lineage:
    return Lineage(
        kind=RevisionKind.WORKFLOW,
        id=WORKFLOW_ID,
    )


def tool() -> Lineage:
    return Lineage(
        kind=RevisionKind.TOOL,
        id=TOOL_ID,
        version="1.0.0",
    )


def test_revision_kinds_are_the_three_revisioned_documents() -> None:
    assert [kind.value for kind in RevisionKind] == ["workflow", "tool", "benchmark"]


def test_a_revision_digest_is_the_sha256_of_its_canonical_identity() -> None:
    expected = hashlib.sha256(
        (
            '{"content":"' + CONTENT + '","format":1,"id":"' + str(WORKFLOW_ID) + '",'
            '"kind":"workflow","parent":null,"version":null}'
        ).encode()
    ).hexdigest()

    assert revision_digest(workflow(), content_digest=CONTENT, parent_digest=None) == expected


def test_the_canonical_identity_names_its_format() -> None:
    assert REVISION_DIGEST_FORMAT == 1


def test_a_root_revision_digest_is_pinned() -> None:
    assert revision_digest(workflow(), content_digest=CONTENT, parent_digest=None) == PINNED_ROOT


def test_a_child_revision_digest_is_pinned() -> None:
    assert revision_digest(workflow(), content_digest=CONTENT, parent_digest=PARENT) == PINNED_CHILD


def test_a_tool_revision_digest_is_pinned() -> None:
    assert revision_digest(tool(), content_digest=CONTENT, parent_digest=None) == PINNED_TOOL


def test_a_revision_digest_matches_the_content_digest_pattern() -> None:
    assert re.fullmatch(
        CONTENT_DIGEST_PATTERN,
        revision_digest(workflow(), content_digest=CONTENT, parent_digest=PARENT),
    )


def test_a_revision_digest_commits_to_its_parent() -> None:
    root = revision_digest(workflow(), content_digest=CONTENT, parent_digest=None)

    child = revision_digest(workflow(), content_digest=CONTENT, parent_digest=PARENT)

    assert root != child


def test_a_revert_differs_from_the_revision_it_reverts_to() -> None:
    first = revision_digest(workflow(), content_digest=CONTENT, parent_digest=None)

    second = revision_digest(workflow(), content_digest=OTHER_CONTENT, parent_digest=first)

    reverted = revision_digest(workflow(), content_digest=CONTENT, parent_digest=second)

    assert reverted not in {first, second}


def test_a_revision_digest_commits_to_its_content() -> None:
    assert revision_digest(
        workflow(), content_digest=CONTENT, parent_digest=None
    ) != revision_digest(workflow(), content_digest=OTHER_CONTENT, parent_digest=None)


def test_a_revision_digest_commits_to_its_kind() -> None:
    benchmark = Lineage(
        kind=RevisionKind.BENCHMARK,
        id=WORKFLOW_ID,
    )

    assert revision_digest(
        benchmark, content_digest=CONTENT, parent_digest=None
    ) != revision_digest(workflow(), content_digest=CONTENT, parent_digest=None)


def test_a_revision_digest_commits_to_its_lineage_id() -> None:
    other = Lineage(
        kind=RevisionKind.WORKFLOW,
        id=TOOL_ID,
    )

    assert revision_digest(other, content_digest=CONTENT, parent_digest=None) != revision_digest(
        workflow(), content_digest=CONTENT, parent_digest=None
    )


def test_a_revision_digest_commits_to_its_tool_version() -> None:
    other = Lineage(
        kind=RevisionKind.TOOL,
        id=TOOL_ID,
        version="1.0.1",
    )

    assert revision_digest(other, content_digest=CONTENT, parent_digest=None) != revision_digest(
        tool(), content_digest=CONTENT, parent_digest=None
    )


def test_a_revision_digest_is_the_same_wherever_it_is_computed() -> None:
    assert revision_digest(
        workflow(), content_digest=CONTENT, parent_digest=PARENT
    ) == revision_digest(
        Lineage.model_validate_json(workflow().model_dump_json()),
        content_digest=CONTENT,
        parent_digest=PARENT,
    )


def test_a_malformed_content_digest_is_refused() -> None:
    with pytest.raises(ValueError) as caught:
        revision_digest(workflow(), content_digest="sha256:" + CONTENT, parent_digest=None)

    assert str(caught.value) == (
        f"Content digest 'sha256:{CONTENT}' is not a lowercase sha256 hex digest."
    )


def test_a_malformed_parent_digest_is_refused() -> None:
    with pytest.raises(ValueError) as caught:
        revision_digest(workflow(), content_digest=CONTENT, parent_digest=PARENT.upper())

    assert str(caught.value) == (
        f"Parent digest '{PARENT.upper()}' is not a lowercase sha256 hex digest."
    )


def test_a_tool_lineage_requires_its_version() -> None:
    with pytest.raises(ValidationError) as caught:
        Lineage(
            kind=RevisionKind.TOOL,
            id=TOOL_ID,
        )

    assert "A tool lineage names its tool version." in str(caught.value)


@pytest.mark.parametrize("kind", [RevisionKind.WORKFLOW, RevisionKind.BENCHMARK])
def test_other_lineages_have_no_version(
    kind: RevisionKind,
) -> None:
    with pytest.raises(ValidationError) as caught:
        Lineage(
            kind=kind,
            id=WORKFLOW_ID,
            version="1.0.0",
        )

    assert f"A {kind.value} lineage has no version." in str(caught.value)


def test_a_tool_version_is_not_empty() -> None:
    with pytest.raises(ValidationError):
        Lineage(
            kind=RevisionKind.TOOL,
            id=TOOL_ID,
            version="",
        )


def test_a_lineage_is_frozen() -> None:
    lineage = workflow()

    field = "id"

    with pytest.raises(ValidationError):
        setattr(lineage, field, TOOL_ID)


def test_a_lineage_refuses_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Lineage.model_validate(
            {
                "kind": "workflow",
                "id": str(WORKFLOW_ID),
                "number": 1,
            }
        )


def test_a_workflow_lineage_is_described_by_its_id() -> None:
    assert str(workflow()) == f"workflow {WORKFLOW_ID}"


def test_a_tool_lineage_is_described_by_its_reference() -> None:
    assert str(tool()) == f"tool {TOOL_ID}@1.0.0"


def test_a_tool_version_is_kept_verbatim_in_the_identity() -> None:
    lineage = Lineage(
        kind=RevisionKind.TOOL,
        id=TOOL_ID,
        version="1.0.0-β",
    )

    expected = hashlib.sha256(
        (
            '{"content":"' + CONTENT + '","format":1,"id":"' + str(TOOL_ID) + '",'
            '"kind":"tool","parent":null,"version":"1.0.0-β"}'
        ).encode()
    ).hexdigest()

    assert revision_digest(lineage, content_digest=CONTENT, parent_digest=None) == expected
