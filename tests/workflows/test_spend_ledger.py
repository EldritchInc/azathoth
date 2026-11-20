"""Tests that spend is a ledger of model calls, each counted once (ADR 0132)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.context import (
    Context,
    active_step_lineage,
    child_lineage,
    create_lineage_event,
)
from azathoth.costs import CostBasis
from azathoth.evaluation import EvaluationEvidence, EvaluationResult, EvaluationStatus
from azathoth.strategies import (
    Strategy,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    InMemoryRunChildRepository,
    InMemoryRunJournalRepository,
    SpendEntry,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowRunner,
    spend_ledger,
)

PARENT_ID = UUID("5e000000-0000-4000-8000-000000000001")

CHILD_ID = UUID("5e000000-0000-4000-8000-000000000002")

PARENT_STEP = UUID("5e000000-0000-4000-8000-000000000003")

CHILD_STEP = UUID("5e000000-0000-4000-8000-000000000004")

JUDGED_AT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def metadata(identifier: UUID) -> StrategyMetadata:
    """Return a strategy's metadata."""

    return StrategyMetadata(id=identifier, name="spend", description="Spend.", version="1.0.0")


class Calling:
    """A step that calls one model, costing what it says, known as it says."""

    def __init__(
        self,
        cost: float | None,
        *,
        provider: str = "openrouter",
        model: str = "acme/small",
        basis: CostBasis | None = "billed",
    ) -> None:
        self._cost = cost
        self._provider = provider
        self._model = model
        self._basis = basis if cost is not None else None

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return metadata(CHILD_STEP)

    async def run(self, context: Context) -> StrategyOutcome:
        """Call the model."""

        del context

        return StrategyOutcome(
            output=1,
            metrics=StrategyExecutionMetrics(
                provider=self._provider,
                model=self._model,
                estimated_cost_usd=self._cost,
                cost_basis=self._basis,
            ),
        )


def workflow(identifier: UUID, step: UUID, strategy: Strategy, name: str) -> WorkflowCandidate:
    """Return a one-step workflow."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(id=identifier, name=name, description="A workflow."),
        steps=(WorkflowCandidateStep(id=step, strategy=strategy),),
    )


class Starting:
    """A step that starts child runs, as `run_workflow` does, keeping each child's run.

    Without `model` it is a tool's step, calling no model; with one it also
    calls that model itself, at `own`.
    """

    def __init__(
        self,
        runner: WorkflowRunner,
        children: list[Calling],
        kept: list[WorkflowRun],
        *,
        own: float | None = 0.0,
        model: str | None = None,
    ) -> None:
        self._runner = runner
        self._children = children
        self._kept = kept
        self._own = own
        self._model = model

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return metadata(PARENT_STEP)

    async def run(self, context: Context) -> StrategyOutcome:
        """Run each child under this step attempt's lineage."""

        del context
        step = active_step_lineage()

        assert step is not None

        for child in self._children:
            self._kept.append(
                await self._runner.run_recording_failures(
                    workflow(CHILD_ID, CHILD_STEP, child, "child"),
                    Context(
                        events=(create_lineage_event(child_lineage(step, workflow_id=CHILD_ID)),)
                    ),
                )
            )

        return StrategyOutcome(
            output=1,
            metrics=StrategyExecutionMetrics(
                provider=None if self._model is None else "openrouter",
                model=self._model,
                estimated_cost_usd=self._own,
                cost_basis=None if self._model is None or self._own is None else "billed",
            ),
        )


def ran(
    *children: Calling,
    own: float | None = 0.0,
    model: str | None = None,
) -> tuple[list[WorkflowRun], InMemoryRunChildRepository]:
    """Run a parent whose one step starts children; return every run, parent first."""

    index = InMemoryRunChildRepository()
    runner = WorkflowRunner(journal=InMemoryRunJournalRepository(), children=index)
    kept: list[WorkflowRun] = []
    parent = asyncio.run(
        runner.run_recording_failures(
            workflow(
                PARENT_ID,
                PARENT_STEP,
                Starting(runner, list(children), kept, own=own, model=model),
                "parent",
            ),
            Context(),
        )
    )

    return [parent, *kept], index


def one_run(strategy: Calling, *, name: str = "solo") -> WorkflowRun:
    """Run a one-step workflow alone."""

    return asyncio.run(
        WorkflowRunner().run_recording_failures(
            workflow(PARENT_ID, CHILD_STEP, strategy, name), Context()
        )
    )


def ledger(
    runs: list[WorkflowRun],
    index: InMemoryRunChildRepository | None = None,
    *,
    production: frozenset[UUID] = frozenset(),
    evaluations: tuple[WorkflowRunEvaluation, ...] = (),
) -> tuple[SpendEntry, ...]:
    """Return the ledger of the runs given."""

    children = index if index is not None else InMemoryRunChildRepository()

    return spend_ledger(
        runs=runs,
        children_of=children.children_of,
        production_run_ids=production,
        evaluations=evaluations,
    )


def judged(run: WorkflowRun, *calls: JsonValue) -> WorkflowRunEvaluation:
    """Return one semantic evaluation of a run, its judges' calls as given."""

    return WorkflowRunEvaluation(
        run_id=run.id,
        evaluated_at=JUDGED_AT,
        evaluation=EvaluationResult(
            evaluator_name="semantic",
            score=1.0,
            status=EvaluationStatus.PASSED,
            reason="It matches.",
            evidence=(EvaluationEvidence(label="judge_calls", value=list(calls)),),
        ),
    )


def call(
    judge: str, cost: float | None, basis: str | None = None, *, replied: bool = True
) -> JsonValue:
    """Return one judge call's evidence record."""

    return {
        "judge": judge,
        "status": "verdict" if replied else "error",
        "detail": None,
        "usage": (
            {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "latency_ms": 5,
                "estimated_cost_usd": cost,
                "cost_basis": basis,
            }
            if replied
            else None
        ),
    }


# A run's calls


def test_each_model_call_is_one_entry_with_its_cost_and_basis() -> None:
    run = one_run(Calling(0.25, model="acme/small", basis="billed"))

    (entry,) = ledger([run])

    assert entry.source == "run"
    assert entry.run_id == run.id
    assert entry.workflow_id == PARENT_ID
    assert entry.workflow_name == "solo"
    assert (entry.provider, entry.model) == ("openrouter", "acme/small")
    assert (entry.cost_usd, entry.cost_basis) == (0.25, "billed")
    assert not entry.unpriced
    assert run.steps[0].execution is not None
    assert entry.at == run.steps[0].execution.completed_at


def test_an_estimated_call_stays_estimated() -> None:
    (entry,) = ledger([one_run(Calling(0.5, provider="bedrock", model="nova", basis="estimated"))])

    assert (entry.provider, entry.cost_basis) == ("bedrock", "estimated")


def test_an_unpriced_call_is_counted_and_never_taken_for_free() -> None:
    (entry,) = ledger([one_run(Calling(None, provider="bedrock", model="nova"))])

    assert entry.unpriced
    assert entry.cost_usd is None
    assert entry.cost_basis is None


def test_a_call_recorded_before_1_5_reads_its_basis_from_its_provider() -> None:
    (entry,) = ledger([one_run(Calling(0.1, basis=None))])

    assert entry.cost_basis == "billed"


def test_a_production_invocations_calls_are_production() -> None:
    run = one_run(Calling(0.25))

    (entry,) = ledger([run], production=frozenset({run.id}))

    assert entry.source == "production"


# Child runs


def test_a_tools_step_calls_no_model_and_its_children_are_counted_for_themselves() -> None:
    runs, index = ran(Calling(0.25, model="acme/child-a"), Calling(0.5, model="acme/child-b"))
    parent, *children = runs

    assert parent.steps[0].execution is not None
    assert parent.steps[0].execution.metrics is not None
    assert parent.steps[0].execution.metrics.estimated_cost_usd == pytest.approx(0.75)

    entries = ledger(runs, index)

    assert [(entry.run_id, entry.model, entry.cost_usd) for entry in entries] == [
        (children[0].id, "acme/child-a", 0.25),
        (children[1].id, "acme/child-b", 0.5),
    ]
    assert sum(entry.cost_usd or 0.0 for entry in entries) == pytest.approx(0.75)


def test_a_model_step_that_started_children_is_entered_at_its_own_cost() -> None:
    runs, index = ran(Calling(0.25, model="acme/child"), own=0.125, model="acme/parent")

    entries = ledger(runs, index)

    assert [(entry.model, entry.cost_usd) for entry in entries] == [
        ("acme/child", 0.25),
        ("acme/parent", pytest.approx(0.125)),
    ]


def test_a_parent_whose_child_is_not_kept_has_an_unknown_cost_of_its_own() -> None:
    runs, index = ran(Calling(0.25, model="acme/child"), own=0.125, model="acme/parent")

    (entry,) = ledger(runs[:1], index)

    assert entry.model == "acme/parent"
    assert entry.unpriced


def test_a_parent_whose_child_is_unpriced_has_an_unknown_cost_of_its_own() -> None:
    runs, index = ran(Calling(None, model="acme/child"), own=0.125, model="acme/parent")
    execution = runs[0].steps[0].execution

    assert execution is not None
    assert execution.metrics is not None
    assert execution.metrics.cost_basis is None

    entries = ledger(runs, index)

    assert [(entry.model, entry.unpriced) for entry in entries] == [
        ("acme/child", True),
        ("acme/parent", True),
    ]


# Judging


def test_each_judge_call_is_judging_on_the_judged_runs_workflow() -> None:
    run = one_run(Calling(0.25), name="judged")
    evaluation = judged(
        run,
        call("openrouter/acme/judge", 0.01, "billed"),
        call("bedrock/nova-judge", 0.02, "estimated"),
    )

    entries = ledger([run], evaluations=(evaluation,))
    judging = [entry for entry in entries if entry.source == "judging"]

    assert [
        (entry.provider, entry.model, entry.cost_usd, entry.cost_basis) for entry in judging
    ] == [
        ("openrouter", "acme/judge", 0.01, "billed"),
        ("bedrock", "nova-judge", 0.02, "estimated"),
    ]
    assert {entry.workflow_name for entry in judging} == {"judged"}
    assert {entry.at for entry in judging} == {JUDGED_AT}
    assert {entry.run_id for entry in judging} == {run.id}


def test_a_judge_call_that_never_replied_spent_nothing_known_and_is_left_out() -> None:
    run = one_run(Calling(0.25))
    evaluation = judged(run, call("openrouter/acme/judge", None, replied=False))

    assert [entry.source for entry in ledger([run], evaluations=(evaluation,))] == ["run"]


def test_an_unpriced_judge_call_is_counted_as_unpriced() -> None:
    run = one_run(Calling(0.25))
    evaluation = judged(run, call("bedrock/nova-judge", None))

    judging = [e for e in ledger([run], evaluations=(evaluation,)) if e.source == "judging"]

    assert [entry.unpriced for entry in judging] == [True]


def test_a_judge_call_recorded_before_1_5_reads_its_basis_from_its_judge() -> None:
    run = one_run(Calling(0.25))
    evaluation = judged(run, call("openrouter/acme/judge", 0.01))

    judging = [e for e in ledger([run], evaluations=(evaluation,)) if e.source == "judging"]

    assert [entry.cost_basis for entry in judging] == ["billed"]


def test_judging_of_a_run_no_longer_kept_is_left_out() -> None:
    run = one_run(Calling(0.25))
    evaluation = judged(run, call("openrouter/acme/judge", 0.01, "billed"))

    assert ledger([], evaluations=(evaluation,)) == ()


# Order


def ending_at(run: WorkflowRun, ended: datetime) -> WorkflowRun:
    """Return a run whose only step ended at `ended`, as a clock may have read it."""

    (step,) = run.steps

    assert step.execution is not None

    execution = step.execution.model_copy(update={"completed_at": ended})

    return run.model_copy(update={"steps": (step.model_copy(update={"execution": execution}),)})


def test_the_ledger_is_in_the_order_the_calls_ended() -> None:
    first = ending_at(one_run(Calling(0.1, model="acme/first")), JUDGED_AT)
    second = ending_at(one_run(Calling(0.2, model="acme/second")), JUDGED_AT + timedelta(seconds=1))

    assert [entry.model for entry in ledger([second, first])] == ["acme/first", "acme/second"]


def test_a_childs_call_ending_in_the_same_instant_as_its_parents_comes_first() -> None:
    #
    # A coarse clock, such as Windows' of about 16 ms, can read a child's
    # call and its parent's step as ending in the same instant.
    #
    runs, index = ran(Calling(0.25, model="acme/child"), own=0.125, model="acme/parent")
    parent, child = runs
    child_execution = child.steps[0].execution

    assert child_execution is not None

    tied = ending_at(parent, child_execution.completed_at)

    assert [entry.model for entry in ledger([tied, child], index)] == [
        "acme/child",
        "acme/parent",
    ]
