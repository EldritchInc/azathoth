"""Tests that every command that invokes checks the promoted workflow's schemas (ADR 0118)."""

import json
from pathlib import Path
from typing import Any

import pytest

import azathoth.cli.bootstrap as cli_bootstrap
from azathoth.cli import main
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
)
from azathoth.tools import LINEAGE_ENVIRONMENT_VARIABLE
from tests.workflows.test_invocation_contract import contracted
from tests.workflows.test_production_invocation_service import PRIMARY, WORKFLOW_ID


def cli(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Run one CLI command; return its status, output and errors."""

    status = main(arguments)
    captured = capsys.readouterr()

    return status, captured.out, captured.err


def answering(
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
) -> None:
    """Make the production model answer with one text."""

    monkeypatch.setattr(
        cli_bootstrap,
        "_load_current_models",
        lambda _configuration: ModelCatalog(
            models=(
                ModelMetadata(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                    display_name=PRIMARY.identifier,
                ),
            )
        ),
    )
    monkeypatch.setattr(
        cli_bootstrap,
        "_load_language_models",
        lambda *, configuration, models: LanguageModelRegistry(
            {
                PRIMARY.identifier: DeterministicLanguageModel(
                    provider=PRIMARY.provider,
                    model=PRIMARY.model,
                    response_text=answer,
                )
            }
        ),
    )


@pytest.fixture
def database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """Initialize a database with the contracted workflow in production."""

    path = tmp_path / "azathoth.db"

    monkeypatch.setenv("AZATHOTH_DATABASE", str(path))
    monkeypatch.delenv("AZATHOTH_CONTENT_STORE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(LINEAGE_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    answering(monkeypatch, "success")

    status, _, err = cli(capsys, "init")

    assert status == 0, err

    open_repositories(path).production_states.set(contracted())

    return path


def invoked(
    capsys: pytest.CaptureFixture[str],
    payload: Any,
) -> dict[str, Any]:
    """Invoke the workflow; return its final JSON lines record."""

    _, out, _ = cli(
        capsys,
        "workflow",
        "invoke",
        str(WORKFLOW_ID),
        "--input",
        json.dumps(payload),
        "--output",
        "jsonl",
    )
    record: dict[str, Any] = json.loads(out.strip().splitlines()[-1])

    return record


def test_an_invocation_that_keeps_its_contract_answers(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = invoked(capsys, {"ticket": "Refund order 0412."})

    assert record["type"] == "result"
    assert record["value"] == {"result": "success"}


def test_workflow_invoke_reports_an_input_that_breaks_the_schema(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = invoked(capsys, {"priority": 1})

    assert record["type"] == "error"
    assert record["code"] == "invalid_input"
    assert record["message"] == (
        "The workflow's input does not match its input schema: $: 'ticket' is a required property."
    )

    (invocation,) = open_repositories(database).invocations.invocations()

    assert open_repositories(database).invocation_runs.get(invocation.id) is None


def test_workflow_invoke_reports_a_result_that_breaks_the_schema_and_keeps_the_run(
    database: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answering(monkeypatch, "failure")

    record = invoked(capsys, {"ticket": "x"})

    assert (record["type"], record["code"]) == ("error", "invalid_output")

    (invocation,) = open_repositories(database).invocations.invocations()
    association = open_repositories(database).invocation_runs.get(invocation.id)

    assert association is not None

    status, out, err = cli(capsys, "invocation", "show", str(invocation.id))

    assert status == 0, err
    assert f"Run ID: {association.run_id}\n" in out
    assert "Outcome: invalid_output\n" in out
    assert (
        "Message: The workflow's result does not match its output schema: $: 'failure' is not "
        "one of ['success'].\n"
    ) in out


def test_a_job_whose_input_breaks_the_schema_fails_and_is_kept(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "request.json").write_text(
        json.dumps(
            {
                "kind": "invoke",
                "version": 1,
                "idempotency_key": "ticket-0412",
                "workflow_id": str(WORKFLOW_ID),
                "input": {"value": {"priority": 1}},
            }
        ),
        encoding="utf-8",
    )

    _, out, _ = cli(capsys, "job", "run", "request.json")
    result = json.loads(out)

    assert result["status"] == "failed", result
    assert result["error"]["code"] == "invalid_input"
    assert result["error"]["metadata"] == {
        "violations": [{"path": "$", "message": "'ticket' is a required property"}]
    }
    assert result["invocation_id"] is not None

    _, replayed, _ = cli(capsys, "job", "run", "request.json")

    assert json.loads(replayed)["replayed"] is True
    assert json.loads(replayed)["error"] == result["error"]
