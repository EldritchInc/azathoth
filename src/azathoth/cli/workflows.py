"""Operational workflow commands for the Azathoth command-line application."""

import asyncio
import json
import sys
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.benchmark_checks import (
    benchmark_has_cases,
    comparisons_supported,
    configured_benchmark,
    results_declared,
)
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.execution import (
    WorkflowRunInput,
    configured_run_context,
    execute_configured_workflow,
)
from azathoth.cli.optimization import optimize_configured_workflow
from azathoth.cli.output_format import (
    DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    WorkflowOutputFormat,
)
from azathoth.cli.production import invoke_active_production_workflow
from azathoth.cli.promotion import (
    WorkflowExperimentNotFoundError,
    promote_configured_workflow,
)
from azathoth.cli.rendering import (
    RESULT_RECORD_TYPE,
    OutputRecord,
    production_invocation_record,
    render_production_invocation_result,
    render_workflow_optimization_session,
    render_workflow_promotion,
    render_workflow_run,
    workflow_run_record,
)
from azathoth.cli.step_output import (
    JsonLinesOutputWriter,
    TextStepMessageWriter,
)
from azathoth.cli.workflow_configuration import (
    export_workflow,
    import_workflow,
    list_workflow_history,
    list_workflows,
    show_workflow,
)
from azathoth.runtime import (
    JudgeUnavailableError,
    WorkflowNotConfiguredError,
)
from azathoth.workflows import (
    ProductionInvocationFailure,
    SQLiteProductionInvocationRepository,
    SQLiteProductionInvocationRunRepository,
    SQLiteWorkflowExperimentRepository,
    SQLiteWorkflowProductionRevisionRepository,
    SQLiteWorkflowProductionStateRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunRepository,
    WorkflowExperimentEvidenceRecorder,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowRunner,
    WorkflowRunObserver,
    WorkflowScoringPolicy,
)


def run_workflow(
    workflow_id: UUID,
    *,
    workflow_input: WorkflowRunInput | None = None,
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
) -> int:
    """Execute one configured workflow and persist its run as evidence.

    Completed runs are persisted whether they succeeded or failed, so configured
    execution history is inspectable alongside production invocation history.
    Runs that never start, because no candidate could be generated, leave no
    evidence.

    Supplied input starts the run with one canonical workflow input event, so
    the run can later become a benchmark case. Without input the run starts
    with an empty context.

    The output format decides what the operator sees while and after the run
    executes. The command returns 0 when the run ends in a result record, and
    1 when it halted or did not produce its declared result.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

    try:
        run = asyncio.run(
            execute_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                context=configured_run_context(workflow_input),
                runner=WorkflowRunner(
                    observer=_step_observer(
                        output,
                        writer,
                    ),
                ),
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

    SQLiteWorkflowRunRepository(
        configuration.database,
    ).save(run)

    if output is WorkflowOutputFormat.TEXT:
        print(render_workflow_run(run))

        return 0 if run.succeeded else 1

    specification = runtime.workflows.get(workflow_id)

    assert specification is not None

    record = workflow_run_record(
        run,
        result=specification.result,
        steps=specification.steps,
    )

    return _write_terminal_record(
        record,
        writer,
    )


def promote_workflow(
    workflow_id: UUID,
    *,
    experiment_id: UUID | None = None,
) -> int:
    """Promote one configured workflow to active production.

    With an experiment ID, the experiment's winner is promoted instead of the
    configured candidate (ADR 0092).
    """

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
            experiment_id=experiment_id,
            experiment_repository=SQLiteWorkflowExperimentRepository(
                configuration.database,
            ),
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowExperimentNotFoundError,
        WorkflowGenerationError,
        WorkflowResultError,
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
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
) -> int:
    """Invoke one active production workflow.

    The output format decides what the caller sees while and after the
    invocation executes. The command returns 0 when the invocation succeeds
    and 1 when it fails.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

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
            runner=WorkflowRunner(
                observer=_step_observer(
                    output,
                    writer,
                ),
            ),
        )
    )

    if output is WorkflowOutputFormat.TEXT:
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

    return _write_terminal_record(
        production_invocation_record(result),
        writer,
    )


def _step_observer(
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
) -> WorkflowRunObserver | None:
    """Return the live step observer of one output format.

    JSON Lines streams step records to stdout through the given writer, text
    prints step messages to stderr, and result mode stays silent.
    """

    if output is WorkflowOutputFormat.JSONL:
        return writer

    if output is WorkflowOutputFormat.TEXT:
        return TextStepMessageWriter(sys.stderr)

    return None


def _write_terminal_record(
    record: OutputRecord,
    writer: JsonLinesOutputWriter | None,
) -> int:
    """Write one terminal record in JSON Lines or result mode, returning the exit code.

    With a writer the record ends the JSON Lines stream. Without one, a result
    record prints only its value as JSON on stdout, and nothing when there is
    no declared result; an error record prints its message on stderr.
    """

    succeeded = record["type"] == RESULT_RECORD_TYPE

    if writer is not None:
        writer.write(record)

    elif not succeeded:
        print(
            record["message"],
            file=sys.stderr,
        )

    elif "value" in record:
        print(
            json.dumps(
                record["value"],
                ensure_ascii=False,
            )
        )

    return 0 if succeeded else 1


def optimize_workflow(
    *,
    workflow_id: UUID,
    benchmark_id: UUID,
    target_latency_seconds: float,
    target_cost_usd: float,
    generations: int,
) -> int:
    """Empirically optimize one configured workflow against a durable benchmark.

    Every candidate runs every benchmark case, and each case judges the
    workflow's declared result with its own comparison. A missing or empty
    benchmark, an unsupported comparison, and a workflow without a declared
    result are rejected before runtime bootstrap, without provider credentials
    and without executing any case.

    Every generation's candidate runs, evaluations, and experiment record are
    saved to the configured database, so the session can be inspected later.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    dataset = configured_benchmark(
        configuration,
        benchmark_id,
    )

    if dataset is None:
        return 1

    if not benchmark_has_cases(dataset):
        return 1

    if not comparisons_supported(
        configuration,
        dataset,
    ):
        return 1

    if not results_declared(
        configuration,
        (workflow_id,),
    ):
        return 1

    runtime = load_runtime(configuration)

    try:
        session = asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                dataset=dataset,
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=target_latency_seconds,
                    target_cost_usd=target_cost_usd,
                ),
                max_generations=generations,
                recorder=WorkflowExperimentEvidenceRecorder(
                    runs=SQLiteWorkflowRunRepository(
                        configuration.database,
                    ),
                    evaluations=SQLiteWorkflowRunEvaluationRepository(
                        configuration.database,
                    ),
                    experiments=SQLiteWorkflowExperimentRepository(
                        configuration.database,
                    ),
                ),
            )
        )
    except (
        WorkflowNotConfiguredError,
        WorkflowGenerationError,
        JudgeUnavailableError,
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
    "export_workflow",
    "import_workflow",
    "invoke_workflow",
    "list_workflow_history",
    "list_workflows",
    "optimize_workflow",
    "promote_workflow",
    "run_workflow",
    "show_workflow",
]
