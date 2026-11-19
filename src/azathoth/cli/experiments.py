"""Workflow experiment inspection commands for the Azathoth CLI.

`workflow experiments` and `experiment show` read through the service API
(ADR 0131), so the command line and every other caller read experiments
the same way. Their output is unchanged.
"""

import sys
from uuid import UUID

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_workflow_experiment,
    render_workflow_experiment_summaries,
)
from azathoth.cli.service import service_instance


def list_workflow_experiments(
    workflow_id: UUID,
    *,
    limit: int | None = None,
) -> int:
    """List persisted experiments containing one workflow, newest first.

    Experiments are listed for workflows that are configured or that appear in
    experiment history, so experiments of a workflow since removed from
    configuration remain inspectable. An identifier with neither fails so
    mistyped identifiers are not mistaken for workflows never optimized.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        experiments = service_instance(configuration).experiments.list(workflow_id, limit=limit)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    if not experiments:
        return 0

    print(render_workflow_experiment_summaries(experiments))

    return 0


def show_experiment(
    experiment_id: UUID,
) -> int:
    """Show one persisted experiment with every observation in rank order."""

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        experiment = service_instance(configuration).experiments.get(experiment_id)
    except api.ApiError as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(render_workflow_experiment(experiment))

    return 0
