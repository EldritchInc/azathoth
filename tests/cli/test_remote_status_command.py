"""Tests for `azathoth remote status` (ADR 0125, ADR 0126)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

import azathoth.cli.application as application
from azathoth.cli import build_parser, main
from azathoth.cli.output_format import StatusOutputFormat
from azathoth.cli.remote import component_line, model_line, status_lines
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import (
    REMOTE_TOKEN_VARIABLE,
    ComponentStatus,
    ModelStatus,
    PortfolioRecord,
    PortfolioResponse,
    Relation,
    RemoteStatus,
)
from azathoth.revisions import AUTHOR_VARIABLE, Lineage, RevisionKind
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_remote_sync_commands import reach
from tests.cli.test_remote_token_commands import ERIS, run
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_closure import CHILD, COUNT_ID, PARENT, PARENT_ID, child, parent
from tests.remote.test_server import Remote

URL = "http://remote.test"

A, B, C = ("a" * 64, "b" * 64, "c" * 64)

WORKFLOW = Lineage(kind=RevisionKind.WORKFLOW, id=PARENT_ID)

TOOL = Lineage(kind=RevisionKind.TOOL, id=COUNT_ID, version="1.0.0")

SYNCED = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)

GUIDE = Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md"


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at a database holding a child workflow and two revisions of its parent."""

    configured = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTHOR_VARIABLE, str(ERIS))
    forbid_runtime(monkeypatch)
    held = open_repositories(configured)
    held.workflows.save(child())
    held.workflows.save(parent())
    held.workflows.save(parent("Counts again."))

    return configured


def unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse every connection the CLI makes, as a remote that is down does."""

    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_token")

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    real = httpx.Client

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **options: real(base_url=URL, transport=httpx.MockTransport(refuse)),
    )


# Parsing


def test_a_status_names_a_remote_what_to_report_and_its_output() -> None:
    parsed = build_parser().parse_args(
        ("remote", "status", "origin", "--workflow", str(PARENT_ID), "--output", "json")
    )

    assert parsed.remote_target == "origin"
    assert parsed.remote_workflows == [PARENT_ID]
    assert parsed.remote_output == "json"
    assert build_parser().parse_args(("remote", "status", "origin")).remote_output == "text"


def test_the_cli_dispatches_a_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def status(**options: object) -> int:
        calls.append(options)
        return 0

    monkeypatch.setattr(application, "remote_status", status)

    assert main(("remote", "status", "origin", "--tool", "x@1", "--output", "json")) == 0
    assert calls == [
        {
            "remote": "origin",
            "workflows": [],
            "tools": ["x@1"],
            "benchmarks": [],
            "output": StatusOutputFormat.JSON,
        }
    ]


# Lines


def test_a_component_line_says_how_it_relates_and_each_sides_latest_revision() -> None:
    assert component_line(
        ComponentStatus(
            lineage=TOOL,
            relation=Relation.AHEAD,
            local_digest=B,
            local_number=2,
            remote_digest=A,
            remote_number=1,
        ),
        reachable=True,
    ) == (f"tool {COUNT_ID}@1.0.0  ahead  here 2 bbbbbbbbbbbb  there 1 aaaaaaaaaaaa")


def test_a_workflow_line_says_what_is_in_production_at_the_remote() -> None:
    running = ComponentStatus(
        lineage=WORKFLOW,
        relation=Relation.BEHIND,
        local_digest=A,
        local_number=1,
        remote_digest=B,
        remote_number=4,
        remote_production_digest=C,
    )

    assert component_line(running, reachable=True) == (
        f"workflow {PARENT_ID}  behind  here 1 aaaaaaaaaaaa  there 4 bbbbbbbbbbbb  "
        "in production there cccccccccccc"
    )
    assert component_line(
        running.model_copy(update={"remote_production_digest": None}),
        reachable=True,
    ).endswith("  not in production there")


def test_a_side_holding_nothing_says_none() -> None:
    assert component_line(
        ComponentStatus(
            lineage=WORKFLOW,
            relation=Relation.REMOTE_ONLY,
            remote_digest=B,
            remote_number=1,
        ),
        reachable=True,
    ) == (
        f"workflow {PARENT_ID}  remote_only  here none  there 1 bbbbbbbbbbbb  "
        "not in production there"
    )
    assert component_line(
        ComponentStatus(lineage=TOOL, relation=Relation.LOCAL_ONLY, local_digest=A, local_number=3),
        reachable=True,
    ) == (f"tool {COUNT_ID}@1.0.0  local_only  here 3 aaaaaaaaaaaa  there none")


def test_a_remote_not_reached_leaves_its_side_and_production_unknown() -> None:
    assert component_line(
        ComponentStatus(lineage=WORKFLOW, relation=None, local_digest=A, local_number=2),
        reachable=False,
    ) == (f"workflow {PARENT_ID}  unknown  here 2 aaaaaaaaaaaa  there unknown")


def test_a_model_line_says_where_it_is_authorized() -> None:
    assert model_line(ModelStatus(identifier="openrouter/example", authorized_locally=True)) == (
        "model openrouter/example  authorized here yes  there unknown"
    )
    assert model_line(
        ModelStatus(
            identifier="bedrock/example",
            authorized_locally=False,
            authorized_remotely=True,
        )
    ) == ("model bedrock/example  authorized here no  there yes")
    assert model_line(
        ModelStatus(
            identifier="bedrock/example",
            authorized_locally=True,
            authorized_remotely=False,
        )
    ).endswith("there no")


def test_a_status_begins_by_saying_whether_the_remote_was_reached() -> None:
    reached = RemoteStatus(remote=URL, reachable=True)

    assert status_lines(reached) == (f"Status of {URL}: reached.",)
    assert status_lines(reached, name="origin") == (f"Status of origin ({URL}): reached.",)
    assert status_lines(RemoteStatus(remote=URL, reachable=False), name="origin") == (
        f"Status of origin ({URL}): not reached; its side is unknown.",
        "Its portfolio was never read here.",
    )
    assert status_lines(RemoteStatus(remote=URL, reachable=False, portfolio_synced_at=SYNCED)) == (
        f"Status of {URL}: not reached; its side is unknown.",
        "Its portfolio is as last read, at 2026-11-12T09:30:00+00:00.",
    )


def test_components_come_before_models() -> None:
    status = RemoteStatus(
        remote=URL,
        reachable=True,
        components=(ComponentStatus(lineage=TOOL, relation=Relation.LOCAL_ONLY),),
        models=(ModelStatus(identifier="openrouter/example", authorized_locally=True),),
    )

    assert [line.split()[0] for line in status_lines(status)] == ["Status", "tool", "model"]


# Reporting


def test_a_status_reports_a_named_remote_after_a_push(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reach(monkeypatch, Remote(tmp_path))
    run(capsys, "remote", "add", "origin", URL)
    run(capsys, "remote", "push", "origin", "--workflow", str(PARENT_ID))

    status, output, errors = run(capsys, "remote", "status", "origin")
    lines = output.splitlines()

    assert (status, errors) == (0, "")
    assert lines[0] == f"Status of origin ({URL}): reached."
    assert sorted(line.split("  ")[:2][0] for line in lines[1:]) == sorted(
        (str(CHILD), str(PARENT))
    )
    assert all(line.split("  ")[1] == "in_sync" for line in lines[1:])
    assert all(line.endswith("  not in production there") for line in lines[1:])


def test_a_status_written_as_json_is_the_apis_remote_status(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reach(monkeypatch, Remote(tmp_path))

    status, output, _ = run(
        capsys, "remote", "status", URL, "--workflow", str(PARENT_ID), "--output", "json"
    )
    reported = RemoteStatus.model_validate_json(output)

    assert status == 0
    assert json.loads(output)["remote"] == URL
    assert reported.reachable is True
    assert [component.relation for component in reported.components] == [Relation.LOCAL_ONLY]
    assert reported.components[0].local_number == 2
    assert reported.components[0].local_digest is not None
    assert len(reported.components[0].local_digest) == 64


def test_a_remote_not_reached_is_a_status_not_a_failure(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    held = open_repositories(database)
    held.remotes.add("origin", URL)
    unreachable(monkeypatch)

    status, output, errors = run(capsys, "remote", "status", "origin", "--workflow", str(PARENT_ID))

    assert (status, errors) == (0, "")
    assert output.splitlines()[:2] == [
        f"Status of origin ({URL}): not reached; its side is unknown.",
        "Its portfolio was never read here.",
    ]
    assert output.splitlines()[2].startswith(f"workflow {PARENT_ID}  unknown  here 2 ")
    assert output.splitlines()[2].endswith("  there unknown")


def test_a_remote_not_reached_reads_its_models_from_its_last_portfolio(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    held = open_repositories(database)
    held.remote_portfolio_snapshots.save(
        URL,
        PortfolioResponse(entries=(PortfolioRecord(identifier="openrouter/example"),)),
    )
    unreachable(monkeypatch)

    status, output, _ = run(capsys, "remote", "status", URL, "--workflow", str(PARENT_ID))
    lines = output.splitlines()

    assert status == 0
    assert lines[1].startswith("Its portfolio is as last read, at ")
    assert lines[-1] == "model openrouter/example  authorized here no  there yes"


def test_a_refused_status_says_why(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_token")

    assert run(capsys, "remote", "status", "origin") == (
        1,
        "",
        "No remote is named 'origin'; name one with `azathoth remote add <NAME> <URL>`.\n",
    )
    assert run(capsys, "remote", "status", URL, "--tool", "word_count@1.0.0") == (
        1,
        "",
        "Tool 'word_count@1.0.0' is not <TOOL_ID>@<VERSION>.\n",
    )


def test_the_guide_quotes_the_status_lines() -> None:
    guide = GUIDE.read_text(encoding="utf-8")

    for line in (
        "Status of <REMOTE>: reached.",
        "Status of <REMOTE>: not reached; its side is unknown.",
        "Its portfolio is as last read, at <TIME>.",
        "Its portfolio was never read here.",
        "<LINEAGE>  <RELATION>  here <NUMBER> <DIGEST>  there <NUMBER> <DIGEST>",
        "model <MODEL>  authorized here yes  there unknown",
    ):
        assert line in guide, line
