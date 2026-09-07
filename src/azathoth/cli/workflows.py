"""Operational workflow commands for the Azathoth command-line application."""

import asyncio
import sys
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.execution import execute_configured_workflow
from azathoth.cli.optimization import optimize_configured_workflow
from azathoth.cli.production import invoke_active_production_workflow
from azathoth.cli.promotion import promote_configured_workflow
from azathoth.cli.rendering import (
    render_production_invocation_result,
    render_workflow_optimization_session,
    render_workflow_promotion,
    render_workflow_run,
)
from azathoth.cli.workflow_configuration import (
    import_workflow,
    list_workflows,
    show_workflow,
)
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.runtime import WorkflowNotConfiguredError
from azathoth.workflows import (
    ProductionInvocationFailure,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunRepository,
    WorkflowGenerationError,
    WorkflowScoringPolicy,
)


def run_workflow(
    workflow_id: UUID,
) -> int:
    """Execute one configured workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    try:
        run = asyncio.run(
            execute_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(render_workflow_run(run))

    return 0 if run.succeeded else 1


def promote_workflow(
    workflow_id: UUID,
) -> int:
    """Promote one configured workflow to active production."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    try:
        revision = promote_configured_workflow(
            runtime=runtime,
            workflow_id=workflow_id,
            production_repository=SQLiteWorkflowProductionStateRepository(
                configuration.database,
            ),
            revision_repository=SQLiteWorkflowProductionRevisionRepository(
                configuration.database,
            ),
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_promotion(
            revision,
        )
    )

    return 0


def invoke_workflow(
    *,
    workflow_id: UUID,
    payload: JsonValue,
) -> int:
    """Invoke one active production workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    result = asyncio.run(
        invoke_active_production_workflow(
            runtime=runtime,
            workflow_id=workflow_id,
            payload=payload,
            invocation_repository=SQLiteProductionInvocationRepository(
                configuration.database,
            ),
            run_repository=SQLiteWorkflowRunRepository(
                configuration.database,
            ),
            invocation_run_repository=SQLiteProductionInvocationRunRepository(
                configuration.database,
            ),
        )
    )

    rendered = render_production_invocation_result(
        result,
    )

    if isinstance(
        result,
        ProductionInvocationFailure,
    ):
        print(
            rendered,
            file=sys.stderr,
        )

        return 1

    print(rendered)

    return 0


def optimize_workflow(
    *,
    workflow_id: UUID,
    expected_value: JsonValue,
    target_latency_seconds: float,
    target_cost_usd: float,
    generations: int,
) -> int:
    """Empirically optimize one configured workflow."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    try:
        session = asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                expected_outcome=ExpectedOutcome(
                    description=("Match the operator-supplied expected value."),
                    value=expected_value,
                    comparison=OutcomeComparison.EXACT,
                ),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=target_latency_seconds,
                    target_cost_usd=target_cost_usd,
                ),
                max_generations=generations,
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        ValueError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1

    print(
        render_workflow_optimization_session(
            session,
        )
    )

    return 0


__all__ = [
    "import_workflow",
    "invoke_workflow",
    "list_workflows",
    "optimize_workflow",
    "promote_workflow",
    "run_workflow",
    "show_workflow",
]
