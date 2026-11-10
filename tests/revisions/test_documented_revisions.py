"""Tests that the revision messages the guides quote are the ones Azathoth prints (ADR 0122)."""

from pathlib import Path
from uuid import UUID

import pytest

from azathoth.revisions import (
    AUTHOR_VARIABLE,
    Author,
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

INSTALL_GUIDE = PROJECT_ROOT / "docs" / "install.md"

LINEAGE_ADR = PROJECT_ROOT / "docs" / "adrs" / "0122-lineage-and-digests.md"


def no_username() -> str:
    raise OSError("No username.")


def malformed_author_message() -> str:
    with pytest.raises(AuthorError) as caught:
        resolve_author({AUTHOR_VARIABLE: "<VALUE>"})

    return str(caught.value)


@pytest.mark.parametrize("guide", (REVISIONS_README, CLI_README, LINEAGE_ADR))
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

    for guide in (REVISIONS_README, LINEAGE_ADR):
        assert f"\n{quoted}\n" in guide.read_text(encoding="utf-8"), guide.name


def test_the_install_guide_quotes_the_author_it_sets_and_the_refusal_it_shows() -> None:
    text = INSTALL_GUIDE.read_text(encoding="utf-8")

    assert 'export AZATHOTH_AUTHOR="Ada Lovelace <ada@example.com>"\n' in text
    assert '$env:AZATHOTH_AUTHOR = "Ada Lovelace <ada@example.com>"\n' in text
    assert f"\nAuthor: {Author.parse('Ada Lovelace <ada@example.com>')}\n" in text

    with pytest.raises(AuthorError) as caught:
        resolve_author({AUTHOR_VARIABLE: "Ada <ada>"})

    assert f"\n{caught.value}\n" in text
