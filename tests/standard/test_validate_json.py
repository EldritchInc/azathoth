"""Tests for the standard validate_json tool."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import JsonValue

from tests.standard.harness import (
    run_standard_tool,
    standard_implementation,
    standard_tool_failure,
)

STORY_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "characters": {
            "type": "array",
            "items": {"type": "object", "required": ["name"]},
        },
    },
    "required": ["title", "characters"],
}

IMPORT_MESSAGE = (
    "validate_json needs the jsonschema package, which Azathoth installs; "
    "run it with the Python that runs Azathoth."
)


def run_without_site_packages(
    tmp_path: Path,
    inputs: dict[str, JsonValue],
) -> subprocess.CompletedProcess[str]:
    """Run validate_json's source with a Python that cannot import jsonschema."""

    script = tmp_path / "validate_json.py"
    script.write_text(standard_implementation("validate_json").source, encoding="utf-8")

    return subprocess.run(
        [sys.executable, "-S", "-I", str(script)],
        input=json.dumps(inputs),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"title": "The Keeper", "characters": []}, id="empty-list"),
        pytest.param(
            {"title": "The Keeper", "characters": [{"name": "Ada"}], "tone": "eerie"},
            id="extra-field",
        ),
    ],
)
def test_validate_json_returns_a_matching_value_unchanged(
    value: JsonValue,
) -> None:
    assert run_standard_tool("validate_json", {"value": value, "schema": STORY_SCHEMA}) == {
        "value": value
    }


def test_validate_json_keeps_non_ascii_text() -> None:
    value: JsonValue = {"title": "Le phare — été", "characters": []}

    assert run_standard_tool("validate_json", {"value": value, "schema": STORY_SCHEMA}) == {
        "value": value
    }


def test_validate_json_accepts_every_value_against_a_true_schema() -> None:
    assert run_standard_tool("validate_json", {"value": [1, None], "schema": True}) == {
        "value": [1, None]
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param(
            {"title": "x", "characters": [{}]},
            "validate_json rejected the value at $.characters[0]: 'name' is a required property.",
            id="nested",
        ),
        pytest.param(
            {"characters": [{}, {}]},
            "validate_json rejected the value at $: 'title' is a required property "
            "(and 2 more errors).",
            id="several",
        ),
        pytest.param(
            {"title": 1, "characters": [{"name": "Ada"}, {}]},
            "validate_json rejected the value at $.characters[1]: 'name' is a required "
            "property (and 1 more error).",
            id="ordered-by-path",
        ),
        pytest.param(
            "no",
            "validate_json rejected the value at $: 'no' is not of type 'object'.",
            id="wrong-type",
        ),
    ],
)
def test_validate_json_fails_with_the_first_violation(
    value: JsonValue,
    message: str,
) -> None:
    assert standard_tool_failure("validate_json", {"value": value, "schema": STORY_SCHEMA}) == (
        1,
        message,
    )


def test_validate_json_rejects_every_value_against_a_false_schema() -> None:
    assert standard_tool_failure("validate_json", {"value": 1, "schema": False}) == (
        1,
        "validate_json rejected the value at $: False schema does not allow 1.",
    )


def test_validate_json_cuts_a_long_violation_short() -> None:
    status, message = standard_tool_failure(
        "validate_json",
        {"value": "a" * 5000, "schema": {"type": "integer"}},
    )

    assert status == 1
    assert message.startswith("validate_json rejected the value at $: 'aaa")
    assert message.endswith("a…")
    assert len(message) < 400


def test_validate_json_keeps_the_count_after_a_long_violation() -> None:
    _, message = standard_tool_failure(
        "validate_json",
        {
            "value": {"a": "x" * 5000, "b": 1},
            "schema": {"properties": {"a": {"type": "integer"}, "b": {"type": "string"}}},
        },
    )

    assert message.endswith("x… (and 1 more error).")


def test_validate_json_follows_the_schemas_dialect() -> None:
    schema: JsonValue = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "items": [{"type": "string"}],
    }

    assert run_standard_tool("validate_json", {"value": ["a", 1], "schema": schema}) == {
        "value": ["a", 1]
    }

    assert standard_tool_failure("validate_json", {"value": [1], "schema": schema}) == (
        1,
        "validate_json rejected the value at $[0]: 1 is not of type 'string'.",
    )


def test_validate_json_does_not_check_formats() -> None:
    assert run_standard_tool(
        "validate_json",
        {"value": "not an email", "schema": {"type": "string", "format": "email"}},
    ) == {"value": "not an email"}


def test_validate_json_resolves_references_within_the_schema() -> None:
    schema: JsonValue = {
        "$defs": {"name": {"type": "string"}},
        "properties": {"name": {"$ref": "#/$defs/name"}},
    }

    assert standard_tool_failure("validate_json", {"value": {"name": 1}, "schema": schema}) == (
        1,
        "validate_json rejected the value at $.name: 1 is not of type 'string'.",
    )


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        pytest.param(
            [],
            "validate_json needs 'schema' to be a JSON Schema: an object or a boolean.",
            id="array",
        ),
        pytest.param(
            {"type": "nope"},
            "validate_json was given an invalid schema: 'nope' is not valid under any of the "
            "given schemas.",
            id="invalid",
        ),
        pytest.param(
            {"$ref": "https://example.com/story.json"},
            "validate_json could not resolve a reference in the schema: "
            "Unresolvable: https://example.com/story.json.",
            id="remote-reference",
        ),
    ],
)
def test_validate_json_rejects_a_schema_it_cannot_use(
    schema: JsonValue,
    message: str,
) -> None:
    assert standard_tool_failure("validate_json", {"value": {}, "schema": schema}) == (2, message)


def test_validate_json_reports_a_missing_local_reference() -> None:
    status, message = standard_tool_failure(
        "validate_json",
        {"value": {}, "schema": {"$ref": "#/$defs/missing"}},
    )

    assert status == 2
    assert message.startswith(
        "validate_json could not resolve a reference in the schema: PointerToNowhere: "
        "'/$defs/missing' does not exist"
    )


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        pytest.param({"schema": True}, "validate_json needs the input 'value'.", id="no-value"),
        pytest.param({"value": 1}, "validate_json needs the input 'schema'.", id="no-schema"),
        pytest.param(
            {"value": 1, "schema": True, "strict": True},
            "validate_json does not take the input 'strict'.",
            id="unknown-input",
        ),
    ],
)
def test_validate_json_names_a_missing_or_unknown_input(
    inputs: dict[str, JsonValue],
    message: str,
) -> None:
    assert standard_tool_failure("validate_json", inputs) == (2, message)


def test_validate_json_explains_a_python_without_jsonschema(
    tmp_path: Path,
) -> None:
    completed = run_without_site_packages(tmp_path, {"value": 1, "schema": True})

    assert completed.returncode == 2
    assert completed.stderr == IMPORT_MESSAGE
    assert completed.stdout == ""
