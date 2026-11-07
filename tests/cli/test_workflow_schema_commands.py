"""Tests that a workflow's schemas are imported, shown and shown in production (ADR 0118)."""

import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from azathoth.cli import import_workflow, render_workflow_production, show_workflow
from azathoth.workflows import (
    SQLiteWorkflowRepository,
)
from tests.cli.test_production_inspection_commands import create_state
from tests.cli.test_workflow_import import (
    WORKFLOW_ID,
    configure_database,
    create_workflow,
)

INPUT_SCHEMA: JsonValue = {
    "type": "object",
    "properties": {"ticket": {"type": "string"}},
    "required": ["ticket"],
}

OUTPUT_SCHEMA: JsonValue = {"type": "string"}


def document(
    **schemas: JsonValue,
) -> str:
    """Return the import test workflow's document, declaring some schemas."""

    return json.dumps({**create_workflow().model_dump(mode="json"), **schemas})


def imported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    **schemas: JsonValue,
) -> tuple[int, str, str]:
    """Import the workflow declaring some schemas; return the status, output and errors."""

    path = tmp_path / "workflow.json"
    path.write_text(document(**schemas), encoding="utf-8")

    configure_database(database=tmp_path / "azathoth.db", monkeypatch=monkeypatch)

    status = import_workflow(path)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


def test_imported_schemas_are_kept_and_shown_after_the_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err = imported(
        tmp_path,
        monkeypatch,
        capsys,
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
    )

    assert status == 0, err

    stored = SQLiteWorkflowRepository(tmp_path / "azathoth.db").get(WORKFLOW_ID)

    assert stored is not None
    assert (stored.input_schema, stored.output_schema) == (INPUT_SCHEMA, OUTPUT_SCHEMA)

    assert show_workflow(WORKFLOW_ID) == 0

    out = capsys.readouterr().out
    after_result = out[out.index("Result: ") :]

    assert after_result.split("\n", 1)[1].startswith(
        "Input Schema:\n"
        + json.dumps(INPUT_SCHEMA, indent=2)
        + "\nOutput Schema:\n"
        + json.dumps(OUTPUT_SCHEMA, indent=2)
        + "\nSteps: 1\n"
    )


def test_a_workflow_with_one_schema_shows_only_that_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err = imported(tmp_path, monkeypatch, capsys, output_schema=OUTPUT_SCHEMA)

    assert status == 0, err
    assert show_workflow(WORKFLOW_ID) == 0

    out = capsys.readouterr().out

    assert "Input Schema:" not in out
    assert "Output Schema:\n" in out


def test_a_workflow_without_schemas_shows_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, _, err = imported(tmp_path, monkeypatch, capsys)

    assert status == 0, err
    assert show_workflow(WORKFLOW_ID) == 0
    assert "Schema:" not in capsys.readouterr().out


def test_a_document_whose_schema_is_not_one_is_refused_saying_why(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert imported(tmp_path, monkeypatch, capsys, input_schema=3) == (
        1,
        "",
        "Workflow document is not a valid WorkflowSpecification. The workflow's input schema "
        "is not usable: A JSON Schema must be an object or a boolean.\n",
    )
    assert not (tmp_path / "azathoth.db").exists()


def test_a_document_with_an_output_schema_and_no_result_is_refused_saying_why(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert imported(tmp_path, monkeypatch, capsys, output_schema=OUTPUT_SCHEMA, result=None) == (
        1,
        "",
        "Workflow document is not a valid WorkflowSpecification. Workflow "
        f"{WORKFLOW_ID} has an output schema, which describes its result, but declares no "
        "result.\n",
    )


def test_production_shows_the_schemas_every_invocation_is_checked_against() -> None:
    state = create_state()

    #
    # The rendering reads the promoted specification as it is; this one
    # declares no result, so its schemas are set without validating it.
    #
    state = state.model_copy(
        update={
            "specification": state.specification.model_copy(
                update={"input_schema": INPUT_SCHEMA, "output_schema": OUTPUT_SCHEMA}
            )
        }
    )

    rendered = render_workflow_production(state, active_revision=None)

    assert (
        "Deployed At: unknown\n"
        "Input Schema:\n"
        + json.dumps(INPUT_SCHEMA, indent=2)
        + "\nOutput Schema:\n"
        + json.dumps(OUTPUT_SCHEMA, indent=2)
        + "\n"
    ) in rendered


def test_production_without_schemas_shows_none() -> None:
    assert "Schema:" not in render_workflow_production(create_state(), active_revision=None)
