"""Contract tests for reading what an instance spent (ADR 0132)."""

import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue

from azathoth import api
from azathoth.context import Context
from azathoth.costs import CostBasis
from azathoth.evaluation import EvaluationEvidence, EvaluationResult, EvaluationStatus
from azathoth.execution import ExecutionResult
from azathoth.persistence.repositories import Repositories, open_repositories
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationRun,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowStepAttempt,
    WorkflowStepRun,
)

WORKFLOW = WorkflowMetadata(
    id=UUID("5e000000-0000-4000-8000-0000000000c1"),
    name="summarize",
    description="Summarize a text.",
)

OTHER = WorkflowMetadata(
    id=UUID("5e000000-0000-4000-8000-0000000000c2"),
    name="translate",
    description="Translate a text.",
)

STEP_ID = UUID("5e000000-0000-4000-8000-0000000000d1")

STRATEGY_ID = UUID("5e000000-0000-4000-8000-0000000000d2")

SINCE = datetime.fromisoformat("2026-11-18T00:00:00-05:00")

UNTIL = datetime.fromisoformat("2026-11-20T00:00:00-05:00")


@pytest.fixture
def repositories(location: str) -> Repositories:
    """Return the instance's repositories."""

    return open_repositories(location)


def keep(
    stored: Repositories,
    when: str,
    cost: float | None,
    *,
    basis: CostBasis | None = "billed",
    provider: str = "openrouter",
    model: str = "acme/small",
    workflow: WorkflowMetadata = WORKFLOW,
) -> WorkflowRun:
    """Keep one run of one step calling `model`, ending when it is said to."""

    ended = datetime.fromisoformat(when)
    execution = ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="prompt",
        strategy_version="1.0.0",
        output="done",
        metrics=StrategyExecutionMetrics(
            provider=provider,
            model=model,
            estimated_cost_usd=cost,
            cost_basis=None if cost is None else basis,
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=ended - timedelta(seconds=1),
        completed_at=ended,
    )
    run = WorkflowRun(
        workflow=workflow,
        steps=(
            WorkflowStepRun(
                step_id=STEP_ID,
                layer_index=0,
                execution=execution,
                attempts=(
                    WorkflowStepAttempt(
                        attempt_number=1,
                        started_at=execution.started_at,
                        completed_at=ended,
                        execution=execution,
                    ),
                ),
            ),
        ),
        initial_context=Context(),
        final_context=Context(),
        started_at=execution.started_at,
        completed_at=ended,
    )
    stored.runs.save(run)

    return run


def invoked(stored: Repositories, run: WorkflowRun) -> None:
    """Record that `run` was a production invocation's."""

    invocation = ProductionInvocation(workflow_id=run.workflow.id, initial_context=Context())
    stored.invocations.save(invocation)
    stored.invocation_runs.save(ProductionInvocationRun(invocation_id=invocation.id, run_id=run.id))


def judged(stored: Repositories, run: WorkflowRun, cost: float, basis: CostBasis) -> None:
    """Record one judge call that judged `run`."""

    call: JsonValue = {
        "judge": "openrouter/acme/judge",
        "status": "verdict",
        "detail": None,
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "latency_ms": 5,
            "estimated_cost_usd": cost,
            "cost_basis": basis,
        },
    }
    stored.run_evaluations.save(
        WorkflowRunEvaluation(
            run_id=run.id,
            evaluated_at=run.completed_at,
            evaluation=EvaluationResult(
                evaluator_name="semantic-judge",
                score=1.0,
                status=EvaluationStatus.PASSED,
                reason="It matches.",
                evidence=(EvaluationEvidence(label="judge_calls", value=[call]),),
            ),
        )
    )


def test_spend_is_reported_by_day_in_the_time_zone_named(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-19T03:00:00+00:00", 0.25)
    keep(repositories, "2026-11-19T15:00:00+00:00", 0.5)

    spent = instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York")

    assert isinstance(spent, api.SpendReport)
    assert [(period.start.isoformat(), period.totals.billed_usd) for period in spent.periods] == [
        ("2026-11-18T00:00:00-05:00", 0.25),
        ("2026-11-19T00:00:00-05:00", 0.5),
    ]
    assert [(group.key, group.label) for group in spent.groups] == [(str(WORKFLOW.id), "summarize")]


def test_billed_and_estimated_are_kept_apart_and_unpriced_calls_counted(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)
    keep(repositories, "2026-11-18T13:00:00-05:00", 0.5, basis="estimated", provider="bedrock")
    keep(repositories, "2026-11-18T14:00:00-05:00", None, provider="bedrock")

    totals = instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York").totals

    assert totals == api.SpendTotals(billed_usd=0.25, estimated_usd=0.5, calls=3, unpriced_calls=1)


def test_production_and_judging_are_their_own_sources(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    benchmarked = keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)
    production = keep(repositories, "2026-11-18T13:00:00-05:00", 0.5)
    invoked(repositories, production)
    judged(repositories, benchmarked, 0.01, "billed")

    spent = instance.spend.report(
        since=SINCE, until=UNTIL, time_zone="America/New_York", group="source"
    )

    assert [(group.key, group.billed_usd) for group in spent.groups] == [
        ("judging", 0.01),
        ("production", 0.5),
        ("run", 0.25),
    ]


def test_one_workflows_spend_alone(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)
    keep(repositories, "2026-11-18T13:00:00-05:00", 0.5, workflow=OTHER)

    spent = instance.spend.report(since=SINCE, until=UNTIL, workflow_id=OTHER.id)

    assert spent.workflow_id == OTHER.id
    assert spent.totals.billed_usd == 0.5


def test_a_workflow_with_no_calls_and_no_configuration_is_not_found(
    instance: api.Azathoth,
) -> None:
    with pytest.raises(api.NotFoundError):
        instance.spend.report(since=SINCE, until=UNTIL, workflow_id=uuid4())


def test_the_time_zone_is_utc_unless_one_is_named(
    instance: api.Azathoth,
) -> None:
    spent = instance.spend.report(since=SINCE, until=UNTIL)

    assert spent.time_zone == "UTC"
    assert spent.since == SINCE
    assert spent.since.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"time_zone": "Mars/Olympus"}, "'Mars/Olympus' is not a time zone"),
        ({"since": UNTIL, "until": SINCE}, "since must not be after until"),
        ({"since": datetime(2026, 11, 18)}, "since must say its offset"),
        ({"period": "fortnight"}, "period must be day, week or month"),
        ({"group": "colour"}, "group must be workflow, model, provider or source"),
    ],
)
def test_what_a_report_cannot_be_made_of_is_an_invalid_argument(
    instance: api.Azathoth,
    changes: dict[str, object],
    message: str,
) -> None:
    arguments: dict[str, object] = {"since": SINCE, "until": UNTIL, **changes}

    with pytest.raises(api.InvalidArgumentError, match=message) as raised:
        instance.spend.report(**arguments)  # type: ignore[arg-type]

    assert raised.value.code == "invalid_argument"


def test_a_report_names_the_command_that_prints_it(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)

    spent = instance.spend.report(
        since=SINCE,
        until=UNTIL,
        period="week",
        group="model",
        time_zone="America/New_York",
        workflow_id=WORKFLOW.id,
    )

    assert spent.command == (
        "azathoth spend --since 2026-11-18T00:00:00-05:00 --until 2026-11-20T00:00:00-05:00"
        f" --by week --group model --time-zone America/New_York --workflow {WORKFLOW.id}"
    )


def test_a_report_is_its_own_json_its_times_with_their_offsets(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)

    spent = instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York")
    text = spent.model_dump_json()

    assert '"since":"2026-11-18T00:00:00-05:00"' in text
    assert api.SpendReport.model_validate_json(text).totals == spent.totals


def test_a_closed_instance_reports_nothing(location: str) -> None:
    opened = api.open(location)
    opened.close()

    with pytest.raises(api.InstanceClosedError):
        opened.spend.report(since=SINCE, until=UNTIL)


def test_spend_reaches_the_runs_kept_in_any_period(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-19T12:00:00-05:00", 0.25)

    spent = instance.spend.report(
        since=datetime(2026, 11, 1, tzinfo=UTC),
        until=datetime(2026, 12, 1, tzinfo=UTC),
        period="month",
    )

    (month,) = spent.periods

    assert month.totals.calls == 1


# CSV


def rows_of(text: str) -> list[dict[str, str]]:
    """Return a CSV document's rows, by its header."""

    return list(csv.DictReader(io.StringIO(text, newline="")))


def test_a_report_as_csv_has_a_header_and_a_row_per_group_in_each_period(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25)
    keep(repositories, "2026-11-18T13:00:00-05:00", 0.5, basis="estimated", workflow=OTHER)
    keep(repositories, "2026-11-18T14:00:00-05:00", None, workflow=OTHER)

    text = api.spend_csv(
        instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York")
    )

    assert text.splitlines()[0] == ",".join(api.SPEND_CSV_COLUMNS)
    assert api.SPEND_CSV_COLUMNS == (
        "period_start",
        "period_end",
        "group",
        "label",
        "billed_usd",
        "estimated_usd",
        "calls",
        "unpriced_calls",
    )
    assert rows_of(text) == [
        {
            "period_start": "2026-11-18T00:00:00-05:00",
            "period_end": "2026-11-19T00:00:00-05:00",
            "group": str(WORKFLOW.id),
            "label": "summarize",
            "billed_usd": "0.25",
            "estimated_usd": "0.0",
            "calls": "1",
            "unpriced_calls": "0",
        },
        {
            "period_start": "2026-11-18T00:00:00-05:00",
            "period_end": "2026-11-19T00:00:00-05:00",
            "group": str(OTHER.id),
            "label": "translate",
            "billed_usd": "0.0",
            "estimated_usd": "0.5",
            "calls": "2",
            "unpriced_calls": "1",
        },
        {
            "period_start": "2026-11-19T00:00:00-05:00",
            "period_end": "2026-11-20T00:00:00-05:00",
            "group": "",
            "label": "",
            "billed_usd": "0.0",
            "estimated_usd": "0.0",
            "calls": "0",
            "unpriced_calls": "0",
        },
    ]


def test_a_csv_ends_each_line_as_rfc_4180_does(
    instance: api.Azathoth,
) -> None:
    text = api.spend_csv(instance.spend.report(since=SINCE, until=UNTIL))

    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")


def test_a_csvs_amounts_are_unrounded(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.000012345678)

    (row, _) = rows_of(
        api.spend_csv(instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York"))
    )

    assert float(row["billed_usd"]) == 0.000012345678


def test_a_label_with_a_comma_or_a_quote_is_quoted(
    repositories: Repositories,
    instance: api.Azathoth,
) -> None:
    named = WorkflowMetadata(
        id=UUID("5e000000-0000-4000-8000-0000000000c3"),
        name='sort, then "rank"',
        description="Sort and rank.",
    )
    keep(repositories, "2026-11-18T12:00:00-05:00", 0.25, workflow=named)

    text = api.spend_csv(
        instance.spend.report(since=SINCE, until=UNTIL, time_zone="America/New_York")
    )

    assert '"sort, then ""rank"""' in text
    assert rows_of(text)[0]["label"] == 'sort, then "rank"'
