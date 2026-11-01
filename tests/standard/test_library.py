"""Tests for the standard tool library that ships in the package (ADR 0095)."""

from importlib.resources import files
from pathlib import Path
from uuid import UUID

import pytest

from azathoth.standard import (
    STANDARD_TOOL_FILES,
    standard_tool_documents,
)
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    ToolDocument,
    decode_tool_document,
    encode_tool_document,
)

PROJECT_ROOT = Path(__file__).parents[2]

EXAMPLES = PROJECT_ROOT / "examples"

STANDARD_TOOLS = PROJECT_ROOT / "src" / "azathoth" / "standard" / "tools"

RETIRED_IMPLEMENTATION_IDS = frozenset(
    {
        # loop_workflow 1.0.0, shipped in Azathoth 1.0 from examples/tools.
        UUID("c1000000-0000-4000-8000-000000000012"),
    }
)


def tool_references(
    documents: tuple[ToolDocument, ...],
) -> list[str]:
    """Return `name@version` for each document, in order."""

    return [f"{document.definition.name}@{document.definition.version}" for document in documents]


def test_standard_documents_load_in_their_fixed_order() -> None:
    assert tool_references(standard_tool_documents()) == [
        "run_workflow@1.0.0",
        "loop_workflow@1.1.0",
        "json_select@1.0.0",
        "json_object@1.0.0",
        "json_merge@1.0.0",
        "validate_json@1.0.0",
    ]


def test_standard_documents_keep_their_tool_ids() -> None:
    assert [document.definition.id for document in standard_tool_documents()] == [
        UUID("c1000000-0000-4000-8000-000000000001"),
        UUID("c1000000-0000-4000-8000-000000000002"),
        UUID("c2000000-0000-4000-8000-000000000001"),
        UUID("c2000000-0000-4000-8000-000000000002"),
        UUID("c2000000-0000-4000-8000-000000000003"),
        UUID("c2000000-0000-4000-8000-000000000004"),
    ]


def test_loading_twice_returns_equal_documents() -> None:
    assert standard_tool_documents() == standard_tool_documents()


def test_the_library_lists_every_packaged_document() -> None:
    packaged = sorted(
        entry.name
        for entry in (files("azathoth.standard") / "tools").iterdir()
        if entry.name.endswith(".json")
    )

    assert packaged == sorted(STANDARD_TOOL_FILES)


@pytest.mark.parametrize(
    "name",
    [pytest.param(name, id=name) for name in STANDARD_TOOL_FILES],
)
def test_standard_documents_are_canonical(
    name: str,
) -> None:
    encoded = (STANDARD_TOOLS / name).read_text(encoding="utf-8")

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")
    assert encoded.endswith("}\n")


def test_loaded_documents_match_the_source_files() -> None:
    from_source = tuple(
        decode_tool_document((STANDARD_TOOLS / name).read_text(encoding="utf-8"))
        for name in STANDARD_TOOL_FILES
    )

    assert standard_tool_documents() == from_source


def test_every_implementation_belongs_to_its_exact_tool_version() -> None:
    for document in standard_tool_documents():
        assert len(document.implementations) > 0

        for implementation in document.implementations:
            assert implementation.tool_id == document.definition.id
            assert implementation.tool_version == document.definition.version


def test_implementation_ids_are_distinct() -> None:
    identifiers = [
        implementation.id
        for document in standard_tool_documents()
        for implementation in document.implementations
    ]

    assert len(identifiers) == len(set(identifiers))


def test_no_implementation_reuses_an_earlier_versions_id() -> None:
    identifiers = {
        implementation.id
        for document in standard_tool_documents()
        for implementation in document.implementations
    }

    assert identifiers.isdisjoint(RETIRED_IMPLEMENTATION_IDS)


def test_standard_implementations_keep_their_ids() -> None:
    assert [
        implementation.id
        for document in standard_tool_documents()
        for implementation in document.implementations
    ] == [
        UUID("c1000000-0000-4000-8000-000000000011"),
        UUID("c1000000-0000-4000-8000-000000000022"),
        UUID("c2000000-0000-4000-8000-000000000011"),
        UUID("c2000000-0000-4000-8000-000000000022"),
        UUID("c2000000-0000-4000-8000-000000000033"),
        UUID("c2000000-0000-4000-8000-000000000044"),
    ]


def test_standard_tools_run_as_python_processes() -> None:
    for document in standard_tool_documents():
        for implementation in document.implementations:
            assert implementation.runtime == PROCESS_TOOL_RUNTIME
            assert implementation.command == ("python",)


def test_only_the_composition_tools_grant_themselves_environment_variables() -> None:
    granting = [
        document.definition.name
        for document in standard_tool_documents()
        for implementation in document.implementations
        if implementation.environment
    ]

    assert granting == ["run_workflow", "loop_workflow"]


@pytest.mark.parametrize(
    "name",
    [pytest.param(name, id=name) for name in STANDARD_TOOL_FILES],
)
def test_standard_tool_sources_never_import_azathoth(
    name: str,
) -> None:
    for implementation in decode_tool_document(
        (STANDARD_TOOLS / name).read_text(encoding="utf-8")
    ).implementations:
        assert "import azathoth" not in implementation.source
        assert "from azathoth" not in implementation.source


def test_no_example_tool_shares_an_identifier_with_a_standard_tool() -> None:
    standard = {
        identifier
        for document in standard_tool_documents()
        for identifier in (
            document.definition.id,
            *(implementation.id for implementation in document.implementations),
        )
    }

    for path in sorted(EXAMPLES.glob("**/tools/*.json")):
        document = decode_tool_document(path.read_text(encoding="utf-8"))
        identifiers = {
            document.definition.id,
            *(implementation.id for implementation in document.implementations),
        }

        assert identifiers.isdisjoint(standard), path.relative_to(PROJECT_ROOT).as_posix()
