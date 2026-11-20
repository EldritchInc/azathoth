"""Spend as a ledger of model calls, each counted once (ADR 0132).

Each entry is one call: a step of a kept run that called a model, or one
call a judge made judging a run. A step that started child runs records its
own call's cost with every child's added in (ADR 0117); the ledger takes the
children's back out, and enters each child run for itself, so every dollar
is counted once, on the model that spent it. A tool's step calls no model,
so only its children are entered.
"""

from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from azathoth.costs import CostBasis
from azathoth.evaluation import judge_call_usages
from azathoth.workflows.execution import WorkflowRun, WorkflowStepRun
from azathoth.workflows.run_children import RunChild
from azathoth.workflows.run_evaluation import WorkflowRunEvaluation

SpendSource = Literal["run", "production", "judging"]
"""Where a call was made: a kept run, a production invocation's run, or a judge."""


class SpendEntry(BaseModel):
    """One model call: when, for which workflow and run, on what, and what it cost."""

    model_config = ConfigDict(frozen=True)

    at: datetime
    """When the call ended: its step's attempt, or its evaluation."""

    source: SpendSource
    workflow_id: UUID
    workflow_name: str
    run_id: UUID
    provider: str | None
    model: str | None
    cost_usd: float | None = Field(ge=0.0)
    """What the call cost, or None when it is unpriced: unknown, never free."""

    cost_basis: CostBasis | None

    @property
    def unpriced(self) -> bool:
        """Return whether nothing is known of what the call cost."""

        return self.cost_usd is None


def run_cost(run: WorkflowRun) -> float | None:
    """Return what a run's executed steps cost, children included, or None if any is unknown.

    It is what the run's journal says it cost (ADR 0117): each executed
    step's recorded cost, summed.
    """

    total = 0.0

    for step in run.steps:
        if step.execution is None:
            continue

        metrics = step.execution.metrics

        if metrics is None or metrics.estimated_cost_usd is None:
            return None

        total += metrics.estimated_cost_usd

    return total


def _own_cost(
    run: WorkflowRun,
    step: WorkflowStepRun,
    cost: float | None,
    *,
    children: tuple[RunChild, ...],
    runs: Mapping[UUID, WorkflowRun],
) -> float | None:
    """Return a step's own cost: what it recorded, less what the children it started cost.

    A child no longer kept, or one whose cost is unknown, leaves the step's
    own cost unknown, since nothing says how much of it was the child's.
    """

    if cost is None:
        return None

    attempt = step.attempts[-1].attempt_number if step.attempts else 1
    started = [
        child
        for child in children
        if child.parent_run_id == run.id
        and child.parent_step_id == step.step_id
        and child.parent_attempt == attempt
    ]
    total = 0.0

    for child in started:
        child_run = runs.get(child.child_run_id)
        child_cost = None if child_run is None else run_cost(child_run)

        if child_cost is None:
            return None

        total += child_cost

    return max(0.0, cost - total)


def _run_entries(
    run: WorkflowRun,
    *,
    source: SpendSource,
    children: tuple[RunChild, ...],
    runs: Mapping[UUID, WorkflowRun],
) -> list[SpendEntry]:
    """Return one entry for each of a run's steps that called a model."""

    entries: list[SpendEntry] = []

    for step in run.steps:
        execution = step.execution

        if execution is None or execution.metrics is None:
            continue

        metrics = execution.metrics

        if metrics.provider is None and metrics.model is None:
            continue

        cost = _own_cost(run, step, metrics.estimated_cost_usd, children=children, runs=runs)

        entries.append(
            SpendEntry(
                at=execution.completed_at,
                source=source,
                workflow_id=run.workflow.id,
                workflow_name=run.workflow.name,
                run_id=run.id,
                provider=metrics.provider,
                model=metrics.model,
                cost_usd=cost,
                cost_basis=None if cost is None else metrics.known_cost_basis,
            )
        )

    return entries


def _judging_entries(
    evaluation: WorkflowRunEvaluation,
    run: WorkflowRun,
) -> list[SpendEntry]:
    """Return one entry for each judge call that replied, judging one run."""

    return [
        SpendEntry(
            at=evaluation.evaluated_at,
            source="judging",
            workflow_id=run.workflow.id,
            workflow_name=run.workflow.name,
            run_id=run.id,
            provider=usage.provider,
            model=usage.model,
            cost_usd=usage.cost_usd,
            cost_basis=usage.known_cost_basis,
        )
        for usage in judge_call_usages(evaluation.evaluation)
    ]


def spend_ledger(
    *,
    runs: Iterable[WorkflowRun],
    children_of: Callable[[UUID], tuple[RunChild, ...]],
    production_run_ids: Collection[UUID],
    evaluations: Iterable[WorkflowRunEvaluation],
) -> tuple[SpendEntry, ...]:
    """Return every model call the kept runs and their judges made, in the order they ended.

    A production invocation's run is `production`, any other kept run
    `run`, and a judge's call `judging`, on the workflow of the run it
    judged. A judge's call on a run no longer kept is left out, since
    nothing says whose it was. Calls that end in the same instant, as a
    coarse clock can read a child's and its parent's, are ordered deepest
    first, since a child ends before the step that started it.
    """

    kept = {run.id: run for run in runs}
    children = {run_id: children_of(run_id) for run_id in kept}
    depths = {child.child_run_id: child.depth for each in children.values() for child in each}
    entries: list[SpendEntry] = []

    for run in kept.values():
        entries.extend(
            _run_entries(
                run,
                source="production" if run.id in production_run_ids else "run",
                children=children[run.id],
                runs=kept,
            )
        )

    for evaluation in evaluations:
        judged = kept.get(evaluation.run_id)

        if judged is not None:
            entries.extend(_judging_entries(evaluation, judged))

    return tuple(sorted(entries, key=lambda entry: (entry.at, -depths.get(entry.run_id, 0))))


__all__ = [
    "SpendEntry",
    "SpendSource",
    "run_cost",
    "spend_ledger",
]
