"""Tests for the standard JSON-shaping tools: json_select, json_object and json_merge."""

import pytest
from pydantic import JsonValue

from tests.standard.harness import (
    run_standard_tool,
    standard_document,
    standard_tool_failure,
)

STORY: JsonValue = {
    "title": "The Keeper",
    "characters": [
        {"name": "Ada", "role": "keeper"},
        {"name": "Tom", "role": "sailor"},
    ],
    "ending": None,
}


# json_select


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param([], STORY, id="empty-path"),
        pytest.param(["title"], "The Keeper", id="object-key"),
        pytest.param(["characters", 0, "name"], "Ada", id="key-index-key"),
        pytest.param(["characters", -1, "role"], "sailor", id="negative-index"),
        pytest.param(["ending"], None, id="null-is-a-value"),
    ],
)
def test_json_select_reads_the_value_at_a_path(
    path: list[JsonValue],
    expected: JsonValue,
) -> None:
    assert run_standard_tool("json_select", {"value": STORY, "path": path}) == {"value": expected}


def test_json_select_keeps_non_ascii_text() -> None:
    assert run_standard_tool(
        "json_select",
        {"value": {"title": "Le phare — été"}, "path": ["title"]},
    ) == {"value": "Le phare — été"}


@pytest.mark.parametrize(
    ("path", "message"),
    [
        pytest.param(
            ["subtitle"],
            "json_select found no value at path [\"subtitle\"]: missing object key 'subtitle'.",
            id="missing-key",
        ),
        pytest.param(
            ["title", "text"],
            'json_select found no value at path ["title", "text"]: missing object key \'text\'.',
            id="key-of-a-string",
        ),
        pytest.param(
            ["title", 0],
            'json_select found no value at path ["title", 0]: expected a list for index 0.',
            id="index-of-a-string",
        ),
        pytest.param(
            ["characters", 2],
            'json_select found no value at path ["characters", 2]: list index 2 is out of range.',
            id="index-out-of-range",
        ),
    ],
)
def test_json_select_fails_when_the_path_holds_nothing(
    path: list[JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("json_select", {"value": STORY, "path": path}) == (1, message)


def test_json_select_returns_the_default_when_the_path_holds_nothing() -> None:
    assert run_standard_tool(
        "json_select",
        {"value": STORY, "path": ["max_chapters"], "default": 18},
    ) == {"value": 18}


def test_json_select_ignores_the_default_when_the_path_holds_a_value() -> None:
    assert run_standard_tool(
        "json_select",
        {"value": STORY, "path": ["title"], "default": "Untitled"},
    ) == {"value": "The Keeper"}


def test_json_select_never_replaces_a_null_with_the_default() -> None:
    assert run_standard_tool(
        "json_select",
        {"value": STORY, "path": ["ending"], "default": "unknown"},
    ) == {"value": None}


def test_json_select_accepts_a_null_default() -> None:
    assert run_standard_tool(
        "json_select",
        {"value": STORY, "path": ["subtitle"], "default": None},
    ) == {"value": None}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("title", id="string"),
        pytest.param([True], id="boolean-segment"),
        pytest.param([1.5], id="float-segment"),
        pytest.param([None], id="null-segment"),
        pytest.param([["title"]], id="nested-list"),
    ],
)
def test_json_select_rejects_a_malformed_path(
    path: JsonValue,
) -> None:
    assert standard_tool_failure("json_select", {"value": STORY, "path": path}) == (
        2,
        "json_select needs 'path' to be a list of object keys and list indexes.",
    )


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param({"path": []}, "json_select needs the input 'value'.", id="no-value"),
        pytest.param({"value": STORY}, "json_select needs the input 'path'.", id="no-path"),
        pytest.param(
            {"value": STORY, "path": [], "paths": []},
            "json_select does not take the input 'paths'.",
            id="unknown-input",
        ),
    ],
)
def test_json_select_names_a_missing_or_unknown_input(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("json_select", inputs) == (2, message)


# json_object


def test_json_object_builds_an_object_from_its_inputs() -> None:
    assert run_standard_tool(
        "json_object",
        {"title": "The Keeper", "chapters": [{"number": 1}], "report": None},
    ) == {"value": {"title": "The Keeper", "chapters": [{"number": 1}], "report": None}}


def test_json_object_keeps_its_inputs_in_order() -> None:
    output = run_standard_tool("json_object", {"b": 1, "a": 2, "c": 3})

    value = output["value"]

    assert isinstance(value, dict)
    assert list(value) == ["b", "a", "c"]


def test_json_object_without_inputs_builds_an_empty_object() -> None:
    assert run_standard_tool("json_object", {}) == {"value": {}}


# json_merge


def test_json_merge_adds_and_replaces_fields() -> None:
    assert run_standard_tool(
        "json_merge",
        {"base": {"a": 1, "b": 2}, "patch": {"b": 3, "c": 4}},
    ) == {"value": {"a": 1, "b": 3, "c": 4}}


def test_json_merge_merges_nested_objects() -> None:
    assert run_standard_tool(
        "json_merge",
        {
            "base": {"settings": {"max_chapters": 18, "timeout": 1800}, "idea": "x"},
            "patch": {"settings": {"max_chapters": 3, "budget": {"seconds": 60}}},
        },
    ) == {
        "value": {
            "settings": {"max_chapters": 3, "timeout": 1800, "budget": {"seconds": 60}},
            "idea": "x",
        }
    }


def test_json_merge_replaces_arrays_instead_of_concatenating_them() -> None:
    assert run_standard_tool(
        "json_merge",
        {"base": {"tags": ["a", "b"]}, "patch": {"tags": ["c"]}},
    ) == {"value": {"tags": ["c"]}}


def test_json_merge_keeps_a_null_in_the_patch_as_a_value() -> None:
    assert run_standard_tool(
        "json_merge",
        {"base": {"ending": "happy", "title": "x"}, "patch": {"ending": None}},
    ) == {"value": {"ending": None, "title": "x"}}


def test_json_merge_replaces_an_object_with_a_scalar_and_a_scalar_with_an_object() -> None:
    assert run_standard_tool(
        "json_merge",
        {"base": {"a": {"x": 1}, "b": 2}, "patch": {"a": 1, "b": {"y": 2}}},
    ) == {"value": {"a": 1, "b": {"y": 2}}}


def test_json_merge_with_an_empty_patch_returns_the_base() -> None:
    assert run_standard_tool(
        "json_merge",
        {"base": {"a": [1, {"b": 2}]}, "patch": {}},
    ) == {"value": {"a": [1, {"b": 2}]}}


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param(
            {"base": [], "patch": {}},
            "json_merge can only merge objects; base is an array.",
            id="array-base",
        ),
        pytest.param(
            {"base": {}, "patch": "x"},
            "json_merge can only merge objects; patch is a string.",
            id="string-patch",
        ),
        pytest.param(
            {"base": {}, "patch": 1.5},
            "json_merge can only merge objects; patch is a number.",
            id="number-patch",
        ),
        pytest.param(
            {"base": True, "patch": {}},
            "json_merge can only merge objects; base is a boolean.",
            id="boolean-base",
        ),
        pytest.param(
            {"base": {}, "patch": None},
            "json_merge can only merge objects; patch is null.",
            id="null-patch",
        ),
    ],
)
def test_json_merge_only_merges_objects(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("json_merge", inputs) == (2, message)


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param({"patch": {}}, "json_merge needs the input 'base'.", id="no-base"),
        pytest.param({"base": {}}, "json_merge needs the input 'patch'.", id="no-patch"),
        pytest.param(
            {"base": {}, "patch": {}, "patches": []},
            "json_merge does not take the input 'patches'.",
            id="unknown-input",
        ),
    ],
)
def test_json_merge_names_a_missing_or_unknown_input(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("json_merge", inputs) == (2, message)


# Shared contract


@pytest.mark.parametrize("name", ["json_select", "json_object", "json_merge"])
def test_json_tools_grant_themselves_no_environment(
    name: str,
) -> None:
    for implementation in standard_document(name).implementations:
        assert implementation.environment == ()
        assert implementation.timeout_seconds == 60.0
