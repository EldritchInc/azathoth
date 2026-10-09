"""One-line workflow run summaries for operator listings."""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from uuid import UUID

from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunFeedbackDisposition,
)

UNJUDGED_RUN_DISPOSITION = "-"


class WorkflowRunSource(StrEnum):
    """Describe which operation produced one persisted workflow run."""

    CONFIGURED = "configured"
    EXPERIMENT = "experiment"
    PRODUCTION = "production"


def render_workflow_run_summaries(
    runs: Iterable[WorkflowRun],
    *,
    run_sources: Mapping[UUID, WorkflowRunSource],
    latest_dispositions: Mapping[UUID, WorkflowRunFeedbackDisposition],
) -> str:
    """Render one line per run in the order given.

    Each line contains the run ID, start time, status, duration, source, and
    the latest feedback disposition. Runs without a known source came from
    configured execution. Runs without feedback show "-".
    """

    return "\n".join(
        _render_summary(
            run,
            source=run_sources.get(run.id, WorkflowRunSource.CONFIGURED),
            disposition=latest_dispositions.get(run.id),
        )
        for run in runs
    )


def _render_summary(
    run: WorkflowRun,
    *,
    source: WorkflowRunSource,
    disposition: WorkflowRunFeedbackDisposition | None,
) -> str:
    """Render one aligned run summary line."""

    status = "succeeded" if run.succeeded else "failed"
    judged = UNJUDGED_RUN_DISPOSITION if disposition is None else disposition.value

    return (
        f"{run.id}  {run.started_at.isoformat()}  {status:<9}  "
        f"{run.duration_seconds:.3f}s  {source.value}  {judged}"
    )
