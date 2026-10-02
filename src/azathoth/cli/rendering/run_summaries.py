"""One-line workflow run summaries for operator listings."""

from collections.abc import Iterable, Set
from uuid import UUID

from azathoth.workflows import WorkflowRun

PRODUCTION_RUN_SOURCE = "production"
CONFIGURED_RUN_SOURCE = "configured"


def render_workflow_run_summaries(
    runs: Iterable[WorkflowRun],
    *,
    production_run_ids: Set[UUID],
) -> str:
    """Render one line per run in the order given.

    Each line contains the run ID, start time, status, duration, and source.
    Runs associated with a production invocation are production runs; every
    other persisted run came from configured execution.
    """

    return "\n".join(
        _render_summary(
            run,
            production=run.id in production_run_ids,
        )
        for run in runs
    )


def _render_summary(
    run: WorkflowRun,
    *,
    production: bool,
) -> str:
    """Render one aligned run summary line."""

    status = "succeeded" if run.succeeded else "failed"
    source = PRODUCTION_RUN_SOURCE if production else CONFIGURED_RUN_SOURCE

    return (
        f"{run.id}  {run.started_at.isoformat()}  {status:<9}  "
        f"{run.duration_seconds:.3f}s  {source}"
    )
