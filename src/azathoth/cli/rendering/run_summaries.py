"""One-line workflow run summaries for operator listings."""

from collections.abc import Iterable, Mapping, Set
from uuid import UUID

from azathoth.workflows import (
    WorkflowRun,
    WorkflowRunFeedbackDisposition,
)

PRODUCTION_RUN_SOURCE = "production"
CONFIGURED_RUN_SOURCE = "configured"
UNJUDGED_RUN_DISPOSITION = "-"


def render_workflow_run_summaries(
    runs: Iterable[WorkflowRun],
    *,
    production_run_ids: Set[UUID],
    latest_dispositions: Mapping[UUID, WorkflowRunFeedbackDisposition],
) -> str:
    """Render one line per run in the order given.

    Each line contains the run ID, start time, status, duration, source, and
    the latest feedback disposition. Runs associated with a production
    invocation are production runs; every other persisted run came from
    configured execution. Runs without feedback show "-".
    """

    return "\n".join(
        _render_summary(
            run,
            production=run.id in production_run_ids,
            disposition=latest_dispositions.get(run.id),
        )
        for run in runs
    )


def _render_summary(
    run: WorkflowRun,
    *,
    production: bool,
    disposition: WorkflowRunFeedbackDisposition | None,
) -> str:
    """Render one aligned run summary line."""

    status = "succeeded" if run.succeeded else "failed"
    source = PRODUCTION_RUN_SOURCE if production else CONFIGURED_RUN_SOURCE
    judged = UNJUDGED_RUN_DISPOSITION if disposition is None else disposition.value

    return (
        f"{run.id}  {run.started_at.isoformat()}  {status:<9}  "
        f"{run.duration_seconds:.3f}s  {source}  {judged}"
    )
