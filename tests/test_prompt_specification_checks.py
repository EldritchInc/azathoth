"""Every prompt-kind check goes through `PROMPT_SPECIFICATIONS`.

The 1.0 promotion bug came from checks that named only `PromptStrategySpec`.
This test keeps the source from listing the prompt kinds by hand, in an
`isinstance` tuple or in a union annotation, so a new prompt kind only has to
be added in `azathoth/prompting/specifications.py`.

Checking a single prompt class stays allowed: that is how code tells the two
kinds apart.
"""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]

SOURCE_ROOT = PROJECT_ROOT / "src" / "azathoth"

DEFINITION = SOURCE_ROOT / "prompting" / "specifications.py"

PROMPT_KINDS = frozenset(
    {
        "PromptStrategySpec",
        "ContextPromptStrategySpec",
    }
)


def _name(node: ast.expr) -> str | None:
    """Return the name a node refers to, as `Name` or `module.Name`."""

    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        return node.attr

    return None


def _union_members(node: ast.expr) -> list[ast.expr]:
    """Flatten an `A | B | C` chain into its members."""

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_union_members(node.left), *_union_members(node.right)]

    return [node]


def _names(nodes: list[ast.expr]) -> set[str]:
    """Return the names a list of nodes refers to."""

    return {name for name in map(_name, nodes) if name is not None}


def _is_hand_written_isinstance(node: ast.Call) -> bool:
    """Return whether a call is `isinstance(x, (... a prompt kind ...))`."""

    if _name(node.func) != "isinstance" or len(node.args) != 2:
        return False

    classes = node.args[1]

    return isinstance(classes, ast.Tuple) and bool(_names(classes.elts) & PROMPT_KINDS)


def _is_hand_written_union(node: ast.expr) -> bool:
    """Return whether a node spells out a union of both prompt kinds."""

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return PROMPT_KINDS.issubset(_names(_union_members(node)))

    if isinstance(node, ast.Subscript) and _name(node.value) == "Union":
        members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]

        return PROMPT_KINDS.issubset(_names(members))

    return False


def hand_written_prompt_checks(source: str) -> list[int]:
    """Return the lines that list the prompt kinds by hand."""

    lines: set[int] = set()

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.expr):
            continue

        is_isinstance = isinstance(node, ast.Call) and _is_hand_written_isinstance(node)

        if is_isinstance or _is_hand_written_union(node):
            lines.add(node.lineno)

    return sorted(lines)


def test_source_has_no_hand_written_prompt_kind_checks() -> None:
    found = [
        f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line}"
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if path != DEFINITION
        for line in hand_written_prompt_checks(path.read_text(encoding="utf-8"))
    ]

    assert found == [], (
        "List the prompt kinds through azathoth.prompting: "
        "isinstance(x, PROMPT_SPECIFICATIONS) for checks, "
        "PromptSpecification for annotations. Found: " + ", ".join(found)
    )


def test_definition_lists_both_prompt_kinds() -> None:
    source = DEFINITION.read_text(encoding="utf-8")

    assert "PROMPT_SPECIFICATIONS: Final = (" in source
    assert "PromptSpecification: TypeAlias = PromptStrategySpec | ContextPromptStrategySpec" in (
        source
    )


def test_flags_a_hand_written_isinstance_tuple() -> None:
    source = "isinstance(spec, (PromptStrategySpec, ContextPromptStrategySpec))\n"

    assert hand_written_prompt_checks(source) == [1]


def test_flags_a_tuple_naming_only_one_prompt_kind() -> None:
    source = "isinstance(spec, (PromptStrategySpec, ToolStepSpecification))\n"

    assert hand_written_prompt_checks(source) == [1]


def test_flags_a_module_qualified_prompt_kind() -> None:
    source = (
        "isinstance(spec, (prompting.PromptStrategySpec, prompting.ContextPromptStrategySpec))\n"
    )

    assert hand_written_prompt_checks(source) == [1]


def test_allows_a_check_against_one_prompt_kind() -> None:
    source = "isinstance(spec, PromptStrategySpec)\nisinstance(spec, ContextPromptStrategySpec)\n"

    assert hand_written_prompt_checks(source) == []


def test_allows_the_shared_definition() -> None:
    source = "isinstance(spec, PROMPT_SPECIFICATIONS)\n"

    assert hand_written_prompt_checks(source) == []


def test_flags_a_union_annotation_of_both_prompt_kinds() -> None:
    source = (
        "def f(\n"
        "    spec: PromptStrategySpec | ContextPromptStrategySpec,\n"
        "    step: PromptStrategySpec | ContextPromptStrategySpec | ToolStepSpecification,\n"
        ") -> None: ...\n"
    )

    assert hand_written_prompt_checks(source) == [2, 3]


def test_flags_a_typing_union_of_both_prompt_kinds() -> None:
    source = "spec: Union[PromptStrategySpec, ContextPromptStrategySpec]\n"

    assert hand_written_prompt_checks(source) == [1]


def test_allows_a_union_with_one_prompt_kind() -> None:
    source = "spec: PromptStrategySpec | ToolStepSpecification\n"

    assert hand_written_prompt_checks(source) == []
