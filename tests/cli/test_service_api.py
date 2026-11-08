"""Tests that the commands the service API covers call it (ADR 0120)."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
import azathoth.cli.tools as tool_commands
import azathoth.cli.workflow_configuration as workflow_commands
from azathoth import api
from azathoth.cli import CliRuntimeConfiguration
from azathoth.cli.service import history_line, identical_note, import_note, service_instance

EXAMPLES = Path(__file__).parents[2] / "examples"

ID = UUID("11111111-1111-1111-1111-111111111111")


class Called(Exception):
    """Raised by the stand-in instance, to show the command reached the API."""


def unreachable(
    _configuration: CliRuntimeConfiguration,
) -> api.Azathoth:
    """Stand in for the service API, failing as soon as a command asks for it."""

    raise Called()


COMMANDS: tuple[tuple[object, Callable[[], int]], ...] = (
    (workflow_commands, lambda: workflow_commands.list_workflow_history(ID)),
    (
        workflow_commands,
        lambda: workflow_commands.import_workflow(EXAMPLES / "workflows" / "simple-prompt.json"),
    ),
    (tool_commands, tool_commands.list_tools),
    (tool_commands, lambda: tool_commands.list_tool_history(ID)),
    (tool_commands, lambda: tool_commands.import_tool(EXAMPLES / "tools" / "word-count.json")),
    (benchmark_commands, benchmark_commands.list_benchmarks),
    (benchmark_commands, lambda: benchmark_commands.list_benchmark_history(ID)),
    (
        benchmark_commands,
        lambda: benchmark_commands.import_benchmark(EXAMPLES / "benchmarks" / "word-count.json"),
    ),
)


@pytest.mark.parametrize(
    ("module", "command"),
    COMMANDS,
    ids=[
        "workflow-history",
        "workflow-import",
        "tool-list",
        "tool-history",
        "tool-import",
        "benchmark-list",
        "benchmark-history",
        "benchmark-import",
    ],
)
def test_the_command_calls_the_service_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module: object,
    command: Callable[[], int],
) -> None:
    monkeypatch.setenv("AZATHOTH_DATABASE", str(tmp_path / "azathoth.db"))
    monkeypatch.setattr(module, "service_instance", unreachable)

    with pytest.raises(Called):
        command()


def test_the_instance_serves_a_database_that_does_not_exist_yet(
    tmp_path: Path,
) -> None:
    configuration = CliRuntimeConfiguration(database=tmp_path / "new.db")

    with service_instance(configuration) as instance:
        assert instance.workflows.list() == ()


def revision(
    *,
    imported_at: datetime | None,
    identical_to: int | None,
) -> api.Revision:
    """Return one revision as the API reports it."""

    return api.Revision(
        number=3,
        content_digest="0123456789abcdef" * 4,
        imported_at=imported_at,
        identical_to=identical_to,
    )


def summary(
    revised: api.Revision,
) -> api.WorkflowSummary:
    """Return one workflow summary at a revision."""

    return api.WorkflowSummary(
        id=ID,
        name="name",
        version="1.0.0",
        description="description",
        revision=revised,
        command="azathoth workflow show",
    )


def test_a_history_line_starts_with_the_number_time_and_digest_prefix() -> None:
    when = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    assert history_line(summary(revision(imported_at=when, identical_to=None))) == (
        "3  2026-11-08T12:00:00+00:00  0123456789ab"
    )
    assert history_line(summary(revision(imported_at=None, identical_to=None))) == (
        "3  unknown  0123456789ab"
    )


def test_a_revert_is_noted_in_history_and_on_import() -> None:
    reverted = revision(imported_at=None, identical_to=1)
    fresh = revision(imported_at=None, identical_to=None)
    detail = api.WorkflowDetail(
        **summary(reverted).model_dump(),
        latest_number=3,
        document={},
    )

    assert identical_note(summary(reverted)) == "  identical to revision 1"
    assert identical_note(summary(fresh)) == ""
    assert import_note(detail) == " (identical to revision 1)"
    assert import_note(detail.model_copy(update={"revision": fresh})) == ""
