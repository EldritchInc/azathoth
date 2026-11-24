"""Tests that the model and tool commands say the same here and on a remote (ADR 0140).

`model list`, `model show`, `model portfolio`, `model authorize`, `model
policy` and `model deauthorize`, and `tool show`, `tool implementations`,
`tool implementation-show`, `tool test-cases`, `tool test-case-show` and
`tool install-standard`, given `--remote` ask that remote's service API.
Since most of them change what they act on, each script of commands is
run twice from the same start: here, over one database, and on a remote
serving a copy of it. What each step printed here is compared with what
it printed there, once the times it recorded are set aside.
"""

import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.cli import main
from azathoth.cli.configuration import OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE
from azathoth.cli.parsing.targets import remote_refusal
from azathoth.evaluation import JudgeEntry
from azathoth.persistence.repositories import open_repositories
from azathoth.providers import (
    ModelCapability,
    ModelModality,
    ModelPricing,
    ProviderModel,
)
from azathoth.revisions import AUTHOR_VARIABLE
from azathoth.tools import (
    McpServer,
    McpToolBinding,
    ToolDocument,
    ToolImplementation,
    ToolTestCase,
    mcp_schema_digest,
)
from azathoth.workflows import WorkflowProductionState
from tests.api.test_models import StaticDirectory, pinned_workflow
from tests.cli.test_remote_option import Reaching
from tests.cli.test_tool_import import IMPLEMENTATION_ID, TOOL_ID, create_definition
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

ALPHA = ProviderModel(
    provider="openrouter",
    model="example/alpha",
    display_name="Alpha",
    input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
    output_modalities=frozenset({ModelModality.TEXT}),
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.STRUCTURED_OUTPUT}),
    context_window_tokens=128_000,
    maximum_output_tokens=16_384,
    pricing=ModelPricing(input_usd_per_million_tokens=1.25, output_usd_per_million_tokens=5.0),
)
"""A model whose provider publishes everything."""

BETA = ProviderModel(provider="openrouter", model="example/beta", display_name="Beta")
"""A model whose provider publishes no limits or prices."""

GAMMA = ProviderModel(provider="openrouter", model="example/gamma", display_name="Gamma")
"""A model to authorize and remove without anything depending on it."""

UNKNOWN_ID = UUID("c1400000-0000-4000-8000-0000000000ff")

TIME_PATTERN = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00")


@dataclass(frozen=True)
class Databases:
    """The database the command line runs on here, and the copy a remote serves."""

    here: Path
    there: Path


@pytest.fixture
def databases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Databases]:
    """Point the command line at a database, and a remote named `origin` at a copy of it.

    The providers here and at the remote serve Alpha, Beta and Gamma.
    """

    here = configure_database(monkeypatch, tmp_path)
    here.touch()

    with api.open(here) as instance:
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)

    there = tmp_path / "remote.db"
    shutil.copyfile(here, there)

    def directory(*_: object, **__: object) -> StaticDirectory:
        return StaticDirectory("openrouter", (ALPHA, BETA, GAMMA))

    monkeypatch.setattr("azathoth.cli.bootstrap.OpenRouterModelDirectory", directory)
    monkeypatch.setattr("azathoth.api.instance.model_directories", lambda _settings: (directory(),))
    monkeypatch.setenv(OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE, "test-openrouter-key")
    monkeypatch.setenv(AUTHOR_VARIABLE, ERIS.name)
    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")
    monkeypatch.setattr(httpx, "Client", Reaching(Served(there, principal=ERIS)))

    yield Databases(here=here, there=there)


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Return what a command exits with and prints, with the times it recorded set aside."""

    status = main(arguments)
    printed = capsys.readouterr()

    return (
        status,
        TIME_PATTERN.sub("<TIME>", printed.out),
        TIME_PATTERN.sub("<TIME>", printed.err),
    )


def scripted(
    capsys: pytest.CaptureFixture[str],
    script: list[tuple[str, ...]],
) -> None:
    """Run a script here, then on the remote, and require every step to say the same."""

    here = [said(capsys, *command) for command in script]
    there = [said(capsys, *command, "--remote", "origin") for command in script]

    for command, step_here, step_there in zip(script, here, there, strict=True):
        assert step_there == step_here, command


def each(
    databases: Databases,
) -> tuple[Path, Path]:
    return databases.here, databases.there


def test_the_models_and_the_portfolio_say_the_same_here_and_on_a_remote(
    databases: Databases,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for path in each(databases):
        repositories = open_repositories(path)
        repositories.production_states.set(
            WorkflowProductionState(specification=pinned_workflow(ALPHA.identifier))
        )
        repositories.judges.add(JudgeEntry(provider="openrouter", model="example/beta"))

    alpha, beta, gamma = ALPHA.identifier, BETA.identifier, GAMMA.identifier
    scripted(
        capsys,
        [
            ("model", "list"),
            ("model", "show", alpha),
            ("model", "show", beta),
            ("model", "show", "openrouter/example/missing"),
            ("model", "portfolio"),
            ("model", "authorize", alpha),
            ("model", "authorize", alpha),
            ("model", "authorize", "openrouter/example/missing"),
            ("model", "authorize", beta, "--no-retention", "--no-training"),
            ("model", "authorize", gamma, "--retains-data", "yes"),
            ("model", "portfolio"),
            ("model", "policy", alpha),
            ("model", "policy", beta),
            ("model", "policy", alpha, "--no-retention"),
            ("model", "policy", alpha, "--no-training"),
            ("model", "policy", "openrouter/example/missing"),
            ("model", "policy", "openrouter/example/missing", "--no-training"),
            ("model", "deauthorize", "openrouter/example/missing"),
            ("model", "deauthorize", alpha),
            ("model", "deauthorize", beta),
            ("model", "deauthorize", beta, "--force"),
            ("model", "deauthorize", gamma),
            ("model", "deauthorize", alpha, "--force"),
            ("model", "portfolio"),
        ],
    )


def test_a_policy_declared_on_a_remote_names_the_caller_as_who_declared_it(
    databases: Databases,
    capsys: pytest.CaptureFixture[str],
) -> None:
    said(capsys, "model", "authorize", ALPHA.identifier, "--remote", "origin")
    status, printed, _ = said(
        capsys, "model", "policy", ALPHA.identifier, "--no-retention", "--remote", "origin"
    )

    with api.open(databases.there) as instance:
        (entry,) = instance.portfolio.list()

    assert status == 0
    assert printed.splitlines() == [
        f"Declared the data policy of model {ALPHA.identifier}.",
        "Retains Data: no",
        "Trains On Data: unknown",
        "Restricted Input: refused",
        f"Declared By: {ERIS.name}",
        "Declared At: <TIME>",
    ]
    assert entry.author is not None
    assert entry.author.name == ERIS.name

    with api.open(databases.here) as instance:
        assert instance.portfolio.list() == ()


def mcp_implementation() -> ToolImplementation:
    """Return an MCP implementation of the word-count tool, with every field it can show."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime="mcp",
        timeout_seconds=2.5,
        environment=("COUNT_TOKEN",),
        mcp=McpToolBinding(
            server=McpServer(command=("npx", "-y", "@acme/count server")),
            tool="count",
            schema_digest=mcp_schema_digest({"type": "object"}, None),
        ),
    )


def test_the_tools_say_the_same_here_and_on_a_remote(
    databases: Databases,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = ToolDocument(
        definition=create_definition(),
        implementations=(mcp_implementation(),),
        test_cases=(
            ToolTestCase(
                tool_id=TOOL_ID,
                name="three words",
                description="Counts three words.",
                inputs={"text": "one two three"},
                expected_output={"count": 3},
            ),
        ),
    )

    for path in each(databases):
        open_repositories(path).tools.save_document(document)

    scripted(capsys, [("tool", "install-standard"), ("tool", "install-standard")])

    with api.open(databases.here) as instance:
        tools = instance.tools.list()
        implementations = [
            implementation
            for tool in tools
            for implementation in instance.tools.implementations(tool.id, tool.version)
        ]
        test_cases = [
            test_case
            for tool_id in dict.fromkeys(tool.id for tool in tools)
            for test_case in instance.tools.test_cases(tool_id)
        ]

    assert any(implementation.runtime != "mcp" for implementation in implementations)
    assert test_cases

    unknown = str(UNKNOWN_ID)
    scripted(
        capsys,
        [
            *(("tool", "show", str(tool.id), "--version", tool.version) for tool in tools),
            ("tool", "show", str(TOOL_ID), "--version", "9.9.9"),
            ("tool", "show", unknown, "--version", "1.0.0"),
            *(
                ("tool", "implementations", str(tool.id), "--version", tool.version)
                for tool in tools
            ),
            ("tool", "implementations", unknown, "--version", "1.0.0"),
            *(
                ("tool", "implementation-show", str(implementation.implementation_id))
                for implementation in implementations
            ),
            ("tool", "implementation-show", unknown),
            *(("tool", "test-cases", str(tool_id)) for tool_id in {str(t.id) for t in tools}),
            ("tool", "test-cases", unknown),
            *(("tool", "test-case-show", str(test_case.test_case_id)) for test_case in test_cases),
            ("tool", "test-case-show", unknown),
        ],
    )


def test_an_mcp_implementation_from_a_remote_shows_its_binding(
    databases: Databases,
    capsys: pytest.CaptureFixture[str],
) -> None:
    open_repositories(databases.there).tools.save_document(
        ToolDocument(definition=create_definition(), implementations=(mcp_implementation(),))
    )

    status, printed, _ = said(
        capsys, "tool", "implementation-show", str(IMPLEMENTATION_ID), "--remote", "origin"
    )

    assert status == 0
    assert printed.splitlines() == [
        f"ID: {IMPLEMENTATION_ID}",
        f"Tool ID: {TOOL_ID}",
        "Tool Version: 1.0.0",
        "Implementation Version: 1.0.0",
        "Runtime: mcp",
        "Timeout: 2.5 seconds",
        "Environment: COUNT_TOKEN",
        "MCP Server: npx -y '@acme/count server'",
        "MCP Tool: count",
        f"Schema Digest: {mcp_schema_digest({'type': 'object'}, None)}",
    ]
    assert said(capsys, "tool", "implementation-show", str(IMPLEMENTATION_ID))[0] == 1


def test_every_model_and_tool_command_but_tool_verify_runs_on_a_remote() -> None:
    for command in (
        "model list",
        "model show",
        "model portfolio",
        "model authorize",
        "model policy",
        "model deauthorize",
        "tool show",
        "tool implementations",
        "tool implementation-show",
        "tool test-cases",
        "tool test-case-show",
        "tool install-standard",
    ):
        assert remote_refusal(command) is None, command

    assert remote_refusal("tool verify") is not None
