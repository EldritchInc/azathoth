"""Tests for `azathoth remote push` and `azathoth remote pull` (ADR 0124)."""

from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

import azathoth.cli.application as application
from azathoth.cli import build_parser, main
from azathoth.cli.remote import tool_versions
from azathoth.persistence.repositories import open_repositories
from azathoth.remote import REMOTE_TOKEN_VARIABLE
from azathoth.revisions import AUTHOR_VARIABLE
from azathoth.sensitivity import Sensitivity
from tests.cli.test_benchmark_add_case import forbid_runtime
from tests.cli.test_remote_token_commands import ERIS, run
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_closure import (
    BENCHMARK,
    BENCHMARK_ID,
    CHILD,
    COUNT_ID,
    PARENT,
    PARENT_ID,
    RUN_ID,
    Instance,
    child,
    parent,
)
from tests.remote.test_pulling import with_benchmark
from tests.remote.test_receiving import CHART, CHART_BYTES
from tests.remote.test_server import Remote

URL = "http://remote.test"


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the CLI at a database holding the child workflow and two revisions of its parent."""

    configured = configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv(AUTHOR_VARIABLE, str(ERIS))
    forbid_runtime(monkeypatch)
    held = open_repositories(configured)
    held.workflows.save(child())
    held.workflows.save(parent())
    held.workflows.save(parent("Counts again."))

    return configured


def reach(
    monkeypatch: pytest.MonkeyPatch,
    remote: Remote,
) -> None:
    """Send the CLI's requests to an in-process remote, with its token in the variable."""

    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, remote.token)

    def served(**options: Any) -> Any:
        return TestClient(remote.client.app)

    monkeypatch.setattr(httpx, "Client", served)


# Parsing


def test_documents_are_named_by_kind_and_given_again_for_more() -> None:
    parsed = build_parser().parse_args(
        (
            "remote",
            "pull",
            URL,
            "--workflow",
            str(PARENT_ID),
            "--workflow",
            str(CHILD.id),
            "--tool",
            f"{COUNT_ID}@1.0.0",
            "--benchmark",
            str(PARENT_ID),
            "--include-restricted",
        )
    )

    assert parsed.remote_url == URL
    assert parsed.remote_workflows == [PARENT_ID, CHILD.id]
    assert parsed.remote_tools == [f"{COUNT_ID}@1.0.0"]
    assert parsed.remote_benchmarks == [PARENT_ID]
    assert parsed.remote_include_restricted is True
    assert build_parser().parse_args(("remote", "push", URL)).remote_workflows == []


def test_a_push_takes_no_restricted_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(("remote", "push", URL, "--include-restricted"))

    assert "--include-restricted" in capsys.readouterr().err


def test_the_cli_dispatches_push_and_pull(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def push(**options: object) -> int:
        calls.append(("push", options))
        return 0

    def pull(**options: object) -> int:
        calls.append(("pull", options))
        return 0

    monkeypatch.setattr(application, "push_to_remote", push)
    monkeypatch.setattr(application, "pull_from_remote", pull)

    assert main(("remote", "push", URL, "--workflow", str(PARENT_ID))) == 0
    assert main(("remote", "pull", URL, "--tool", "x@1")) == 0
    assert calls == [
        ("push", {"url": URL, "workflows": [PARENT_ID], "tools": [], "benchmarks": []}),
        (
            "pull",
            {
                "url": URL,
                "workflows": [],
                "tools": ["x@1"],
                "benchmarks": [],
                "include_restricted": False,
            },
        ),
    ]


def test_tool_versions_are_an_id_and_a_version() -> None:
    assert tool_versions((f"{COUNT_ID}@1.0.0",)) == ((COUNT_ID, "1.0.0"),)

    for value in ("word_count@1.0.0", f"{COUNT_ID}", f"{COUNT_ID}@"):
        with pytest.raises(ValueError) as caught:
            tool_versions((value,))

        assert str(caught.value) == f"Tool {value!r} is not <TOOL_ID>@<VERSION>."


# Pushing


def test_a_push_reports_what_the_remote_received(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    remote = Remote(tmp_path)
    reach(monkeypatch, remote)

    status, out, err = run(capsys, "remote", "push", URL, "--workflow", str(PARENT_ID))
    lines = out.splitlines()

    assert (status, err) == (0, "")
    assert lines[0] == (
        f"Pushed to {URL}. Revisions received: 3. Revisions already held: 0. Content sent: 0."
    )
    assert lines[1:4] == [
        f"Received {CHILD} as revision 1.",
        f"Received {PARENT} as revision 1.",
        f"Received {PARENT} as revision 2.",
    ]
    assert lines[4].startswith("Not gathered: Step ")


def test_a_refused_push_says_why(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts differently."))
    reach(monkeypatch, Remote(tmp_path, held=theirs))

    status, out, err = run(capsys, "remote", "push", URL, "--workflow", str(PARENT_ID))

    assert (status, out) == (1, "")
    assert err.startswith(f"Workflow {PARENT_ID} has diverged: ")
    assert err.endswith(" Pull first, then push again.\n")


@pytest.mark.parametrize("action", ["push", "pull"])
def test_without_a_token_nothing_travels(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    monkeypatch.delenv(REMOTE_TOKEN_VARIABLE, raising=False)

    assert run(capsys, "remote", action, URL, "--workflow", str(PARENT_ID)) == (
        1,
        "",
        "No remote token was given; set AZATHOTH_REMOTE_TOKEN to one created on the remote "
        "with `azathoth remote token create`.\n",
    )


@pytest.mark.parametrize("action", ["push", "pull"])
def test_naming_nothing_sends_nothing(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    reach(monkeypatch, Remote(tmp_path))

    assert run(capsys, "remote", action, URL) == (
        1,
        "",
        "Name a workflow, tool version or benchmark to send.\n",
    )


@pytest.mark.parametrize("action", ["push", "pull"])
def test_a_malformed_tool_sends_nothing(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    reach(monkeypatch, Remote(tmp_path))

    assert run(capsys, "remote", action, URL, "--tool", "word_count") == (
        1,
        "",
        "Tool 'word_count' is not <TOOL_ID>@<VERSION>.\n",
    )


def test_a_remote_not_reached_says_so(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(REMOTE_TOKEN_VARIABLE, "azr_token")

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    real = httpx.Client

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **options: real(base_url=URL, transport=httpx.MockTransport(refuse)),
    )

    assert run(capsys, "remote", "push", URL, "--workflow", str(PARENT_ID)) == (
        1,
        "",
        f"The remote at {URL} could not be reached: Connection refused\n",
    )


# Pulling


def test_a_pull_reports_what_it_saved_and_forked(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    theirs = Instance()
    theirs.workflows.save(child())
    theirs.workflows.save(parent())
    theirs.workflows.save(parent("Counts at the remote."))
    reach(monkeypatch, Remote(tmp_path, held=theirs))

    status, out, err = run(capsys, "remote", "pull", URL, "--workflow", str(PARENT_ID))
    lines = out.splitlines()

    assert (status, err) == (0, "")
    assert lines[0] == (
        f"Pulled from {URL}. Revisions saved: 3. Revisions already held: 1. Content fetched: 0."
    )
    assert lines[1:5] == [
        f"Saved tool {COUNT_ID}@1.0.0 as revision 1.",
        f"Saved tool {RUN_ID}@1.0.0 as revision 1.",
        f"Saved {PARENT} as revision 3.",
        f"Forked {PARENT}: its pulled revisions build on an earlier revision here.",
    ]
    assert lines[5].startswith("Not gathered at the remote: Step ")


def test_a_pull_withholds_a_restricted_benchmark_unless_asked_for_it(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    theirs = with_benchmark(Instance(), Sensitivity.RESTRICTED)
    theirs.content.put(CHART_BYTES)
    reach(monkeypatch, Remote(tmp_path, held=theirs, accepts_restricted=True))

    withheld = run(capsys, "remote", "pull", URL, "--benchmark", str(BENCHMARK_ID))

    assert withheld == (
        0,
        f"Pulled from {URL}. Revisions saved: 0. Revisions already held: 0. Content fetched: "
        f"0.\nWithheld {BENCHMARK}: it is restricted; pull it with --include-restricted.\n",
        "",
    )

    included = run(
        capsys,
        "remote",
        "pull",
        URL,
        "--benchmark",
        str(BENCHMARK_ID),
        "--include-restricted",
    )

    assert included == (
        0,
        f"Pulled from {URL}. Revisions saved: 1. Revisions already held: 0. Content fetched: "
        f"1.\nSaved {BENCHMARK} as revision 1.\n",
        "",
    )
    assert open_repositories(database).content.get(CHART.digest) == CHART_BYTES


def test_the_guide_quotes_the_report_lines_and_refusals() -> None:
    readme = (Path(__file__).parents[2] / "src" / "azathoth" / "cli" / "README.md").read_text(
        encoding="utf-8"
    )

    for line in (
        "Pushed to <URL>. Revisions received: <COUNT>. Revisions already held: <COUNT>. "
        "Content sent: <COUNT>.",
        "Pulled from <URL>. Revisions saved: <COUNT>. Revisions already held: <COUNT>. "
        "Content fetched: <COUNT>.",
        "Forked <LINEAGE>: its pulled revisions build on an earlier revision here.",
        "Withheld <LINEAGE>: it is restricted; pull it with --include-restricted.",
        "Tool '<VALUE>' is not <TOOL_ID>@<VERSION>.",
    ):
        assert f"\n{line}\n" in readme
