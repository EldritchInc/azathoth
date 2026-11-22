"""Tests that Azathoth shows a remote's edition and never acts on it (ADR 0134).

A remote's policy names its edition, and may say more of it. Any plugin may
name any edition, so nothing in Azathoth unlocks, hides or changes anything
by what an edition is called: what a remote may do is its policy's to say.
This reads every module Azathoth ships and fails on any comparison, or match,
of an edition.
"""

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]

SHIPPED = (PROJECT_ROOT / "src", PROJECT_ROOT / "packages")


EDITION_ENDINGS = ("edition", "edition_detail")
"""How the name of an edition, or of what a policy says of it, ends: `DEFAULT_EDITION`."""


def names_an_edition(
    node: ast.expr,
) -> bool:
    """Return whether an expression is an edition or its detail: a name, attribute or call.

    A name that only mentions one, such as the longest a detail may be, is
    not one.
    """

    if isinstance(node, ast.Name):
        return node.id.lower().endswith(EDITION_ENDINGS)

    if isinstance(node, ast.Attribute):
        return node.attr.lower().endswith(EDITION_ENDINGS)

    if isinstance(node, ast.Call):
        return names_an_edition(node.func)

    return False


def comparisons_of_editions(
    source: str,
) -> list[int]:
    """Return the lines on which source compares or matches an edition."""

    found: list[int] = []

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(
            names_an_edition(operand) for operand in (node.left, *node.comparators)
        ):
            found.append(node.lineno)

        if isinstance(node, ast.Match) and names_an_edition(node.subject):
            found.append(node.lineno)

    return found


def shipped_modules() -> list[Path]:
    """Return every module Azathoth ships, outside its tests."""

    return sorted(
        path
        for root in SHIPPED
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and "tests" not in path.parts
    )


def test_no_shipped_module_acts_on_an_edition() -> None:
    modules = shipped_modules()

    assert modules
    assert [
        f"{path.relative_to(PROJECT_ROOT)}:{line}"
        for path in modules
        for line in comparisons_of_editions(path.read_text(encoding="utf-8"))
    ] == []


@pytest.mark.parametrize(
    "source",
    [
        "if policy.edition == 'team':\n    pass\n",
        "allowed = DEFAULT_EDITION != capabilities.edition\n",
        "if seams.edition_detail is None:\n    pass\n",
        "known = remote.edition in EDITIONS\n",
        "match remote.edition:\n    case _:\n        pass\n",
    ],
)
def test_acting_on_an_edition_would_be_found(
    source: str,
) -> None:
    assert comparisons_of_editions(source) == [1]


def test_showing_an_edition_is_not_acting_on_it() -> None:
    assert comparisons_of_editions("print(f'edition {capabilities.edition}')\n") == []


def test_checking_a_details_length_is_not_acting_on_an_edition() -> None:
    assert comparisons_of_editions("too_long = len(detail) > MAX_EDITION_DETAIL_LENGTH\n") == []
