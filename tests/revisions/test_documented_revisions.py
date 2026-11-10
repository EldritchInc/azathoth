"""Tests that the revision messages the guides quote are the ones Azathoth prints (ADR 0122)."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.revisions import (
    AUTHOR_VARIABLE,
    AuthorError,
    BaseRevisionError,
    Lineage,
    RevisionKind,
    base_record,
    resolve_author,
)

PROJECT_ROOT = Path(__file__).parents[2]

REVISIONS_README = PROJECT_ROOT / "src" / "azathoth" / "revisions" / "README.md"

CLI_README = PROJECT_ROOT / "src" / "azathoth" / "cli" / "README.md"


def no_username() -> str:
    raise OSError("No username.")


def malformed_author_message() -> str:
    with pytest.raises(AuthorError) as caught:
        resolve_author({AUTHOR_VARIABLE: "<VALUE>"})

    return str(caught.value)


@pytest.mark.parametrize("guide", (REVISIONS_README, CLI_README))
def test_a_malformed_author_variable_is_quoted_exactly(
    guide: Path,
) -> None:
    assert f"\n{malformed_author_message()}\n" in guide.read_text(encoding="utf-8")


def test_no_usable_author_is_quoted_exactly() -> None:
    with pytest.raises(AuthorError) as caught:
        resolve_author({}, username=no_username)

    assert f"\n{caught.value}\n" in REVISIONS_README.read_text(encoding="utf-8")


def test_an_unknown_base_revision_is_quoted_exactly() -> None:
    lineage = Lineage(
        kind=RevisionKind.WORKFLOW,
        id=UUID("11111111-1111-1111-1111-111111111111"),
    )

    with pytest.raises(BaseRevisionError) as caught:
        base_record((), lineage, "<DIGEST>")

    quoted = str(caught.value).replace(str(lineage.id), "<WORKFLOW_ID>")

    assert f"\n{quoted}\n" in REVISIONS_README.read_text(encoding="utf-8")
