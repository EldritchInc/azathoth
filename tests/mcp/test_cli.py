"""Tests for the `azathoth-mcp` command (ADR 0111)."""

import asyncio
import json
import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path
from uuid import UUID

import pytest
from mcp import Client, StdioServerParameters

from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp import __version__
from azathoth_mcp.cli import (
    EXPOSURE_ENVIRONMENT_VARIABLE,
    NO_EXPOSURE_MESSAGE,
    exposure_path,
    main,
)

WORKFLOW_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

UNPROMOTED_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")


def production_state() -> WorkflowProductionState:
    """Return a one-step workflow whose model no provider offers."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=WORKFLOW_ID,
                name="cli-workflow",
                description="Exercise the command.",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=UUID(int=1),
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=UUID(int=2),
                            name="cli-step",
                            description="Exercise the command.",
                        ),
                        prompt=Prompt(text="Summarize."),
                        model_selection=FixedModelSelection(
                            provider="openrouter", model="nobody/offers-this"
                        ),
                    ),
                ),
            ),
        ),
    )


def prepared(
    tmp_path: Path,
    *workflow_ids: UUID,
) -> tuple[Path, Path]:
    """Return a database with the workflow active, and an exposure document listing some."""

    database = tmp_path / "azathoth.db"
    open_repositories(database).production_states.set(production_state())

    exposure = tmp_path / "exposure.json"
    exposure.write_text(
        json.dumps(
            {
                "version": 1,
                "tools": [
                    {"workflow_id": str(workflow_id), "name": f"tool-{index}", "description": "T."}
                    for index, workflow_id in enumerate(workflow_ids or (WORKFLOW_ID,))
                ],
            }
        ),
        encoding="utf-8",
    )

    return database, exposure


def server_environment(
    database: Path,
) -> dict[str, str]:
    """Return an environment that names a database and configures no provider."""

    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("AZATHOTH_", "OPENROUTER_", "OTEL_", "AWS_"))
    }
    environment["AZATHOTH_DATABASE"] = str(database)

    return environment


def run_command(
    *arguments: str,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run `python -m azathoth_mcp` with some arguments, and no input."""

    return subprocess.run(
        [sys.executable, "-m", "azathoth_mcp", *arguments],
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_the_command_is_installed_as_a_console_script() -> None:
    (script,) = (
        entry_point
        for entry_point in entry_points(group="console_scripts")
        if entry_point.name == "azathoth-mcp"
    )

    assert script.value == "azathoth_mcp.cli:main"


def test_the_version_is_this_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert capsys.readouterr().out == f"azathoth-mcp {__version__}\n"


def test_the_argument_names_the_document_before_the_environment() -> None:
    environment = {EXPOSURE_ENVIRONMENT_VARIABLE: "from-environment.json"}

    assert exposure_path(Path("argument.json"), environment) == Path("argument.json")
    assert exposure_path(None, environment) == Path("from-environment.json")
    assert exposure_path(None, {}) is None
    assert exposure_path(None, {EXPOSURE_ENVIRONMENT_VARIABLE: ""}) is None


def test_serving_needs_an_exposure_document(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(EXPOSURE_ENVIRONMENT_VARIABLE, raising=False)

    assert main(["serve"]) == 2

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == f"{NO_EXPOSURE_MESSAGE}\n"
    assert NO_EXPOSURE_MESSAGE == (
        "Name the exposure document to serve with --exposure or AZATHOTH_MCP_EXPOSURE."
    )


def test_only_stdio_is_served_so_far(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["serve", "--exposure", "x.json", "--transport", "http"])

    assert raised.value.code == 2
    assert "invalid choice: 'http'" in capsys.readouterr().err


def test_a_missing_document_stops_the_server(
    tmp_path: Path,
) -> None:
    database, _ = prepared(tmp_path)
    missing = tmp_path / "missing.json"

    completed = run_command(
        "serve", "--exposure", str(missing), environment=server_environment(database)
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == f"No exposure document at {missing}.\n"


def test_an_unpromoted_workflow_stops_the_server(
    tmp_path: Path,
) -> None:
    database, exposure = prepared(tmp_path, WORKFLOW_ID, UNPROMOTED_ID)

    completed = run_command(
        "serve", "--exposure", str(exposure), environment=server_environment(database)
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        "Every exposed workflow must be active in production; these are not: "
        f'"tool-1" ({UNPROMOTED_ID}). Promote each one before exposing it.\n'
    )


def test_the_environment_names_the_document_when_no_argument_does(
    tmp_path: Path,
) -> None:
    database, _ = prepared(tmp_path)
    environment = server_environment(database)
    environment[EXPOSURE_ENVIRONMENT_VARIABLE] = str(tmp_path / "named.json")

    completed = run_command("serve", environment=environment)

    assert completed.returncode == 1
    assert completed.stderr == f"No exposure document at {tmp_path / 'named.json'}.\n"


def test_a_provider_that_cannot_be_used_stops_the_server_before_it_serves(
    tmp_path: Path,
) -> None:
    database, exposure = prepared(tmp_path)
    environment = server_environment(database)

    #
    # Bedrock is on, in a region given here rather than by the machine's AWS
    # profile, with a pricing document that does not exist. Without boto3 it
    # is unavailable, and with it misconfigured; either way, before anything
    # reaches AWS.
    #
    environment["AZATHOTH_BEDROCK"] = "1"
    environment["AWS_REGION"] = "us-east-1"
    environment["AZATHOTH_BEDROCK_PRICING"] = str(tmp_path / "missing-pricing.json")

    completed = run_command("serve", "--exposure", str(exposure), environment=environment)

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.strip()
    assert completed.stderr.count("\n") == 1


def test_a_client_that_closes_at_once_ends_the_server_cleanly(
    tmp_path: Path,
) -> None:
    database, exposure = prepared(tmp_path)

    completed = run_command(
        "serve", "--exposure", str(exposure), environment=server_environment(database)
    )

    assert completed.returncode == 0
    assert completed.stdout == ""


def test_a_client_calls_the_server_over_stdio(
    tmp_path: Path,
) -> None:
    database, exposure = prepared(tmp_path)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "azathoth_mcp", "serve", "--exposure", str(exposure)],
        env=server_environment(database),
    )

    async def use() -> tuple[list[str], dict[str, object] | None, bool | None]:
        async with Client(parameters) as client:
            names = [tool.name for tool in (await client.list_tools()).tools]
            result = await client.call_tool("tool-0", {"input": "x", "idempotency_key": "k-1"})

            return names, result.structured_content, result.is_error

    names, outcome, is_error = asyncio.run(use())

    assert names == ["tool-0", "get_invocation"]
    assert is_error is True
    assert outcome is not None
    assert outcome["status"] == "failed"
    assert outcome["idempotency_key"] == "k-1"
    assert outcome["error"] == {
        "code": "model_unavailable",
        "message": "The production model is unavailable.",
        "metadata": {},
    }

    invocation = open_repositories(database).invocations.invocation_for_idempotency_key("k-1")

    assert invocation is not None
    assert invocation.caller_metadata == {"mcp": {"transport": "stdio", "tool": "tool-0"}}
