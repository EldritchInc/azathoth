"""Tests for the exposure document (ADR 0111)."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth_mcp.exposure import (
    GET_INVOCATION_TOOL,
    RESERVED_TOOL_NAMES,
    ExposedWorkflow,
    ExposureDocument,
    ExposureDocumentError,
    decode_exposure,
    load_exposure,
    parse_exposure,
)

SUMMARIZE_ID = "7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44"

TRIAGE_ID = "0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708"


def tool(
    **changes: JsonValue,
) -> dict[str, JsonValue]:
    """Return one valid tool entry, with some fields changed or added."""

    entry: dict[str, JsonValue] = {
        "workflow_id": SUMMARIZE_ID,
        "name": "summarize_ticket",
        "description": "Summarize a support ticket in three sentences.",
    }
    entry.update(changes)

    return entry


def without(
    entry: dict[str, JsonValue],
    key: str,
) -> dict[str, JsonValue]:
    """Return one entry without one of its keys."""

    return {name: value for name, value in entry.items() if name != key}


def document(
    *tools: JsonValue,
) -> dict[str, JsonValue]:
    """Return an exposure document of version 1 holding some tools."""

    return {"version": 1, "tools": list(tools)}


def refusal(
    data: JsonValue,
) -> str:
    """Return the message decoding some data is refused with."""

    with pytest.raises(ExposureDocumentError) as raised:
        decode_exposure(data)

    return str(raised.value)


def test_a_valid_document_decodes_every_tool_in_order() -> None:
    schema: dict[str, JsonValue] = {"type": "object", "required": ["ticket"]}

    decoded = decode_exposure(
        document(
            tool(input_schema=schema),
            tool(workflow_id=TRIAGE_ID, name="triage.ticket-v2", description="Triage it."),
        )
    )

    assert decoded == ExposureDocument(
        version=1,
        tools=(
            ExposedWorkflow(
                workflow_id=UUID(SUMMARIZE_ID),
                name="summarize_ticket",
                description="Summarize a support ticket in three sentences.",
                input_schema=schema,
            ),
            ExposedWorkflow(
                workflow_id=UUID(TRIAGE_ID),
                name="triage.ticket-v2",
                description="Triage it.",
            ),
        ),
    )


def test_a_tool_without_an_input_schema_has_none() -> None:
    (decoded,) = decode_exposure(document(tool())).tools

    assert decoded.input_schema is None


def test_a_boolean_input_schema_is_accepted() -> None:
    (decoded,) = decode_exposure(document(tool(input_schema=True))).tools

    assert decoded.input_schema is True


def test_tools_are_found_by_name() -> None:
    decoded = decode_exposure(document(tool(), tool(workflow_id=TRIAGE_ID, name="triage")))

    found = decoded.tool_named("triage")

    assert found is not None
    assert found.workflow_id == UUID(TRIAGE_ID)
    assert decoded.tool_named("summarize") is None


def test_the_document_is_immutable() -> None:
    decoded = decode_exposure(document(tool()))

    with pytest.raises(ValidationError, match="Instance is frozen"):
        decoded.tools[0].__setattr__("name", "other")


def test_a_document_must_be_an_object() -> None:
    assert refusal([tool()]) == "An exposure document must be a JSON object."


def test_a_document_must_name_its_version() -> None:
    assert refusal({"tools": [tool()]}) == "An exposure document must name its version."


@pytest.mark.parametrize(
    ("version", "shown"),
    [("1", '"1"'), (1.0, "1.0"), (True, "true"), (None, "null")],
)
def test_a_version_must_be_an_integer(
    version: JsonValue,
    shown: str,
) -> None:
    assert refusal({"version": version, "tools": [tool()]}) == (
        f"An exposure document's version must be an integer; got {shown}."
    )


def test_another_version_is_unsupported_before_its_fields_are_read() -> None:
    assert refusal({"version": 2, "shape": "unknown"}) == (
        "Exposure document version 2 is not supported; supported versions: 1."
    )


def test_a_document_must_list_its_tools() -> None:
    assert refusal({"version": 1}) == "The exposure document is not valid: tools: is required"


def test_tools_must_be_a_list() -> None:
    assert refusal({"version": 1, "tools": "summarize_ticket"}) == (
        "The exposure document is not valid: tools: must be a list"
    )


def test_a_document_must_expose_something() -> None:
    assert refusal(document()) == (
        "The exposure document is not valid: tools: "
        "An exposure document must expose at least one workflow."
    )


def test_unknown_fields_are_refused_in_a_document_and_in_a_tool() -> None:
    assert refusal({**document(tool(scope="admin")), "server": "x"}) == (
        "The exposure document is not valid: tools[0].scope: is not a field of this document; "
        "server: is not a field of this document"
    )


def test_a_tool_must_be_an_object() -> None:
    assert refusal(document(tool(), "triage")) == (
        "The exposure document is not valid: tools[1]: must be an object"
    )


@pytest.mark.parametrize("key", ["workflow_id", "name", "description"])
def test_every_tool_field_but_the_schema_is_required(
    key: str,
) -> None:
    assert refusal(document(without(tool(), key))) == (
        f"The exposure document is not valid: tools[0].{key}: is required"
    )


@pytest.mark.parametrize(
    ("workflow_id", "shown"),
    [("summarize", '"summarize"'), (7, "7"), (None, "null")],
)
def test_a_workflow_id_must_be_a_uuid(
    workflow_id: JsonValue,
    shown: str,
) -> None:
    assert refusal(document(tool(workflow_id=workflow_id))) == (
        "The exposure document is not valid: tools[0].workflow_id: "
        f"A workflow ID must be a UUID; got {shown}."
    )


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("", '""'),
        ("summarize ticket", '"summarize ticket"'),
        ("résumé", '"r\\u00e9sum\\u00e9"'),
        ("a/b", '"a/b"'),
        ("x" * 65, json.dumps("x" * 65)),
        (5, "5"),
    ],
)
def test_a_tool_name_must_be_one_every_client_accepts(
    name: JsonValue,
    shown: str,
) -> None:
    assert refusal(document(tool(name=name))) == (
        "The exposure document is not valid: tools[0].name: "
        f'A tool name holds 1 to 64 letters, digits, "_", "-" or "."; got {shown}.'
    )


def test_a_tool_name_may_be_64_characters() -> None:
    (decoded,) = decode_exposure(document(tool(name="x" * 64))).tools

    assert decoded.name == "x" * 64


def test_the_server_keeps_get_invocation_for_itself() -> None:
    assert GET_INVOCATION_TOOL in RESERVED_TOOL_NAMES
    assert refusal(document(tool(name=GET_INVOCATION_TOOL))) == (
        "The exposure document is not valid: tools[0].name: "
        'The tool name "get_invocation" is kept for the server\'s own tool.'
    )


@pytest.mark.parametrize("description", ["", "   ", "\n\t"])
def test_a_description_must_not_be_blank(
    description: str,
) -> None:
    assert refusal(document(tool(description=description))) == (
        "The exposure document is not valid: tools[0].description: "
        "A tool's description must not be blank."
    )


def test_a_description_must_be_text() -> None:
    assert refusal(document(tool(description=["Summarize."]))) == (
        "The exposure document is not valid: tools[0].description: "
        'A tool\'s description must be text; got ["Summarize."].'
    )


def test_an_input_schema_must_be_an_object_or_a_boolean() -> None:
    assert refusal(document(tool(input_schema="object"))) == (
        "The exposure document is not valid: tools[0].input_schema: "
        "A JSON Schema must be an object or a boolean."
    )


def test_an_input_schema_must_satisfy_its_metaschema() -> None:
    message = refusal(document(tool(input_schema={"type": "ticket"})))

    assert message.startswith(
        "The exposure document is not valid: tools[0].input_schema: Invalid JSON Schema: "
    )


def test_a_tool_name_is_used_once() -> None:
    assert refusal(document(tool(), tool(workflow_id=TRIAGE_ID))) == (
        "The exposure document is not valid: tools: "
        'The tool name "summarize_ticket" is used more than once.'
    )


def test_a_workflow_is_exposed_once() -> None:
    assert refusal(document(tool(), tool(name="summarize_again"))) == (
        "The exposure document is not valid: tools: "
        f"The workflow {SUMMARIZE_ID} is exposed more than once."
    )


def test_a_workflow_id_is_compared_as_a_uuid() -> None:
    assert refusal(document(tool(), tool(workflow_id=SUMMARIZE_ID.upper(), name="other"))) == (
        "The exposure document is not valid: tools: "
        f"The workflow {SUMMARIZE_ID} is exposed more than once."
    )


def test_every_problem_is_reported_at_once() -> None:
    assert refusal(document(tool(name="bad name"), without(tool(), "description"))) == (
        "The exposure document is not valid: "
        "tools[0].name: "
        'A tool name holds 1 to 64 letters, digits, "_", "-" or "."; got "bad name".; '
        "tools[1].description: is required"
    )


def test_text_is_parsed_with_or_without_a_byte_order_mark() -> None:
    text = json.dumps(document(tool()))

    assert parse_exposure(text) == decode_exposure(document(tool()))
    assert parse_exposure("﻿" + text) == decode_exposure(document(tool()))
    assert parse_exposure(text.encode("utf-8")) == decode_exposure(document(tool()))
    assert parse_exposure(b"\xef\xbb\xbf" + text.encode("utf-8")) == decode_exposure(
        document(tool())
    )


def test_bytes_must_be_utf_8() -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        parse_exposure(b"\xff\xfe{}")

    assert str(raised.value) == "An exposure document must be UTF-8 text."


def test_text_must_be_json() -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        parse_exposure('{"version": 1,\n  tools: []}')

    assert str(raised.value) == (
        "An exposure document must be JSON: "
        "Expecting property name enclosed in double quotes at line 2, column 3."
    )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_numbers_json_does_not_define_are_refused(
    constant: str,
) -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        parse_exposure(f'{{"version": {constant}}}')

    assert str(raised.value) == (
        f"An exposure document must be JSON: {constant} is not a JSON number."
    )


def test_text_is_decoded_as_data_is() -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        parse_exposure("[]")

    assert str(raised.value) == "An exposure document must be a JSON object."


def test_a_file_is_loaded(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "exposure.json", json.dumps(document(tool())))

    assert load_exposure(path) == decode_exposure(document(tool()))


def test_a_missing_file_is_named(
    tmp_path: Path,
) -> None:
    path = tmp_path / "exposure.json"

    with pytest.raises(ExposureDocumentError) as raised:
        load_exposure(path)

    assert str(raised.value) == f"No exposure document at {path}."


def test_a_file_that_cannot_be_read_is_named(
    tmp_path: Path,
) -> None:
    with pytest.raises(ExposureDocumentError) as raised:
        load_exposure(tmp_path)

    assert str(raised.value).startswith(f"Cannot read the exposure document {tmp_path}: ")
    assert str(raised.value).endswith(".")


def test_an_invalid_file_is_named_before_its_problem(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "exposure.json", json.dumps(document()))

    with pytest.raises(ExposureDocumentError) as raised:
        load_exposure(path)

    assert str(raised.value) == (
        f"{path}: The exposure document is not valid: tools: "
        "An exposure document must expose at least one workflow."
    )


def write(
    path: Path,
    text: str,
) -> Path:
    """Write some UTF-8 text to one file and return its path."""

    path.write_text(text, encoding="utf-8")

    return path
