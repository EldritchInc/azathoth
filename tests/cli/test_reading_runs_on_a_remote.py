"""Tests that the commands reading workflows and runs say the same here and on a remote (ADR 0140).

`workflow list`, `workflow show`, `workflow runs` and `run show` read the
service API. Each is run over one database twice, once on this machine and
once with `--remote` on a remote serving that database, and must print
the same. The renderers of the API's views must render a run as the
renderers of a kept run always did.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from azathoth import api
from azathoth.cli import (
    main,
    render_workflow_run,
    render_workflow_run_evaluations,
    render_workflow_run_feedback,
)
from azathoth.cli.parsing.targets import remote_refusal
from azathoth.cli.rendering.run_details import (
    render_run_detail,
    render_run_evaluations,
    render_run_feedback,
)
from azathoth.context import (
    Context,
    LineageRun,
    LineageStep,
    WorkflowLineage,
    create_lineage_event,
)
from azathoth.evaluation import EvaluationEvidence, EvaluationResult, EvaluationStatus
from azathoth.persistence.repositories import open_repositories
from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
)
from tests.api.test_runs import COUNT_WORKFLOW_ID, MISSING_ID, stock
from tests.cli.test_confidence_rendering import with_confidence
from tests.cli.test_remote_option import Reaching
from tests.cli.test_rendering import failed_run, successful_run
from tests.cli.test_run_resource_rendering import run_with_resources, tool_binding
from tests.cli.test_workflow_run import configure_database
from tests.remote.test_call_routes import ERIS, Served

URL = "http://remote.test"

TOKEN_VARIABLE = "AZATHOTH_ORIGIN_TOKEN"

PARENT_RUN_ID = UUID("c1400000-0000-4000-8000-0000000000a1")

ROOT_RUN_ID = UUID("c1400000-0000-4000-8000-0000000000a2")

PARENT_STEP_ID = UUID("c1400000-0000-4000-8000-0000000000a3")

EVALUATED_AT = datetime(2026, 11, 2, 12, 5, tzinfo=UTC)

JUDGED_AT = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


def child(
    run: WorkflowRun,
) -> WorkflowRun:
    """Return a run as a step of another run started it, two runs below its root."""

    lineage = create_lineage_event(
        WorkflowLineage(
            depth=2,
            parent=LineageStep(
                workflow_id=run.workflow.id,
                run_id=PARENT_RUN_ID,
                step_id=PARENT_STEP_ID,
                attempt=2,
            ),
            root=LineageRun(workflow_id=run.workflow.id, run_id=ROOT_RUN_ID),
        )
    )

    return run.model_copy(update={"initial_context": Context(events=(lineage,))})


KEPT: dict[str, Callable[[], WorkflowRun]] = {
    "succeeded": successful_run,
    "failed": failed_run,
    "resources": lambda: run_with_resources(tool_binding()),
    "confidence": lambda: with_confidence(successful_run(), 0.62),
    "child": lambda: child(successful_run()),
}


def kept(
    path: Path,
    run: WorkflowRun,
) -> api.RunDetail:
    """Keep a run in a database of its own, and return the service API's view of it."""

    open_repositories(path).runs.save(run)

    with api.open(path) as instance:
        return instance.runs.get(run.id)


@pytest.mark.parametrize("name", sorted(KEPT))
def test_a_run_the_api_returns_renders_as_the_kept_run_does(
    tmp_path: Path,
    name: str,
) -> None:
    run = KEPT[name]()
    path = tmp_path / "azathoth.db"
    path.touch()

    assert render_run_detail(kept(path, run), children=3) == render_workflow_run(
        run,
        children=3,
    )


def test_a_runs_judgments_the_api_returns_render_as_the_kept_ones_do(
    tmp_path: Path,
) -> None:
    run = successful_run()
    path = tmp_path / "azathoth.db"
    path.touch()
    repositories = open_repositories(path)
    repositories.runs.save(run)
    evaluation = WorkflowRunEvaluation(
        run_id=run.id,
        evaluated_at=EVALUATED_AT,
        evaluation=EvaluationResult(
            evaluator_name="exact-match",
            evaluator_version="2.0.0",
            score=0.25,
            threshold=1.0,
            status=EvaluationStatus.FAILED,
            reason="Actual value did not exactly match expected value at $.result.",
            evidence=(
                EvaluationEvidence(label="expected", value={"result": "Ünknown"}),
                EvaluationEvidence(label="difference_path", value="$.result"),
            ),
        ),
    )
    repositories.run_evaluations.save(evaluation)
    judgments = (
        WorkflowRunFeedback(
            run_id=run.id,
            disposition=WorkflowRunFeedbackDisposition.GOOD,
            created_at=JUDGED_AT,
        ),
        WorkflowRunFeedback(
            run_id=run.id,
            disposition=WorkflowRunFeedbackDisposition.BAD,
            reason="It missed the point.",
            corrected_output={"result": 2},
            created_at=JUDGED_AT.replace(hour=14),
        ),
    )

    for judgment in judgments:
        repositories.feedback.save(judgment)

    with api.open(path) as instance:
        detail = instance.runs.get(run.id)
        feedback = instance.runs.feedback(run.id)

    assert render_run_evaluations(detail.evaluations) == render_workflow_run_evaluations(
        (evaluation,)
    )
    assert render_run_feedback(tuple(reversed(feedback))) == render_workflow_run_feedback(judgments)


# The same here and on a remote


@pytest.fixture
def database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Point the command line at a database with runs of every kind, naming `origin` its remote."""

    configured = configure_database(monkeypatch, tmp_path)
    configured.touch()

    with api.open(configured) as instance:
        stock(instance)
        instance.remotes.add("origin", URL, token_variable=TOKEN_VARIABLE)
        instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="one two"))
        judged = instance.runs.run(COUNT_WORKFLOW_ID, input=api.RunInput(payload="one"))
        instance.runs.record_feedback(judged.run_id, "bad", reason="Too short.")
        instance.runs.run(
            COUNT_WORKFLOW_ID,
            input=api.RunInput(payload="one two three"),
            sensitivity=api.Sensitivity.RESTRICTED,
        )
        benchmark = instance.benchmarks.create("words", "Counts words.").benchmark.id
        instance.benchmarks.add_case(
            benchmark,
            input=api.RunInput(payload="a b"),
            comparison="exact",
            expected={"result": 2},
        )
        instance.benchmarks.run(benchmark, COUNT_WORKFLOW_ID)

    monkeypatch.setenv(TOKEN_VARIABLE, "azr_origin")
    monkeypatch.setattr(httpx, "Client", Reaching(Served(configured, principal=ERIS)))

    return configured


def said(
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str, str]:
    """Return what a command exits with and prints, to standard output and to standard error."""

    status = main(arguments)
    printed = capsys.readouterr()

    return status, printed.out, printed.err


def run_ids(
    path: Path,
) -> list[UUID]:
    with api.open(path) as instance:
        return [run.run_id for run in instance.runs.list(COUNT_WORKFLOW_ID)]


def commands(
    path: Path,
) -> list[tuple[str, ...]]:
    """Return every command this commit reads through the service API, with what it reads."""

    workflow = str(COUNT_WORKFLOW_ID)

    return [
        ("workflow", "list"),
        ("workflow", "show", workflow),
        ("workflow", "show", workflow, "--revision", "1"),
        ("workflow", "show", workflow, "--revision", "9"),
        ("workflow", "show", str(MISSING_ID)),
        ("workflow", "runs", workflow),
        ("workflow", "runs", workflow, "--limit", "2"),
        ("workflow", "runs", str(MISSING_ID)),
        *(("run", "show", str(run_id)) for run_id in run_ids(path)),
        ("run", "show", str(MISSING_ID)),
    ]


def test_each_reading_command_says_the_same_here_and_on_a_remote(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in commands(database):
        here = said(capsys, *command)
        there = said(capsys, *command, "--remote", "origin")

        assert there == here, command


def test_the_runs_of_a_workflow_name_what_made_them_and_their_latest_judgment(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, printed, _ = said(
        capsys, "workflow", "runs", str(COUNT_WORKFLOW_ID), "--remote", "origin"
    )
    sources = [line.split()[-2] for line in printed.splitlines()]
    judged = [line.split()[-1] for line in printed.splitlines()]

    assert status == 0
    assert sources == ["benchmark", "configured", "configured", "configured"]
    assert sorted(judged) == ["-", "-", "-", "bad"]


def test_a_restricted_run_shown_from_a_remote_warns_as_it_does_here(
    database: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    restricted = run_ids(database)[1]
    status, printed, warned = said(capsys, "run", "show", str(restricted), "--remote", "origin")

    assert status == 0
    assert "Sensitivity: restricted\n" in printed
    assert warned == f"Run {restricted} is restricted; its output contains restricted data.\n"


def test_the_commands_that_read_workflows_and_runs_now_run_on_a_remote() -> None:
    for command in ("workflow list", "workflow show", "workflow runs", "run show"):
        assert remote_refusal(command) is None, command
