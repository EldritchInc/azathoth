"""Workflow experiment inspection commands for the Azathoth CLI."""

import sys
from uuid import UUID

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.rendering import (
    render_workflow_experiment,
    render_workflow_experiment_summaries,
)
from azathoth.workflows import (
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowRepository,
)


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

    experiments = SQLiteWorkflowExperimentRepository(
        configuration.database,
    ).experiments_for_workflow(workflow_id)

    if (
        not experiments
        and SQLiteWorkflowRepository(
            configuration.database,
        ).get(workflow_id)
        is None
    ):
        print(
            f"Workflow {workflow_id} is not configured.",
            file=sys.stderr,
        )

        return 1

    newest_first = sorted(
        experiments,
        key=lambda experiment: experiment.recorded_at,
        reverse=True,
    )

    if limit is not None:
        newest_first = newest_first[:limit]

    if not newest_first:
        return 0

    print(render_workflow_experiment_summaries(newest_first))

    return 0


def show_experiment(
    experiment_id: UUID,
) -> int:
    """Show one persisted experiment with every observation in rank order."""

    configuration = CliRuntimeConfiguration.from_environment()

    experiment = SQLiteWorkflowExperimentRepository(
        configuration.database,
    ).get(experiment_id)

    if experiment is None:
        print(
            f"Experiment {experiment_id} was not found.",
            file=sys.stderr,
        )

        return 1

    print(render_workflow_experiment(experiment))

    return 0
