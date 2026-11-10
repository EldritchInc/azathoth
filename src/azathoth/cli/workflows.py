"""Operational workflow commands for the Azathoth command-line application."""

import asyncio
import sys
from dataclasses import replace
from typing import Final
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.benchmark_checks import (
    benchmark_has_cases,
    comparisons_supported,
    configured_benchmark,
    results_declared,
)
from azathoth.cli.benchmark_execution import case_runner
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.execution import (
    WorkflowRunInput,
    configured_run_context,
    execute_configured_workflow,
)
from azathoth.cli.inputs import (
    WorkflowInputFile,
    resolve_input_file,
)
from azathoth.cli.keyed_invocation import invoke_with_key
from azathoth.cli.lineage import parent_lineage
from azathoth.cli.optimization import optimize_configured_workflow
from azathoth.cli.output_format import (
    DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    WorkflowOutputFormat,
)
from azathoth.cli.persistence import repositories
from azathoth.cli.production import invoke_active_production_workflow
from azathoth.cli.promotion import (
    WorkflowExperimentNotFoundError,
    promote_configured_workflow,
)
from azathoth.cli.rendering import (
    render_workflow_optimization_session,
    render_workflow_promotion,
)
from azathoth.cli.reporting import (
    report_configured_run,
    report_invocation_result,
    step_observer,
)
from azathoth.cli.step_output import (
    JsonLinesOutputWriter,
)
from azathoth.cli.tracing import run_traced
from azathoth.cli.workflow_configuration import (
    export_workflow,
    import_workflow,
    list_workflow_history,
    list_workflows,
    show_workflow,
)
from azathoth.inputs import (
    InputProvenance,
    InputResolutionError,
    InputSourceError,
)
from azathoth.runtime import (
    JudgeUnavailableError,
    WorkflowNotConfiguredError,
)
from azathoth.sensitivity import Sensitivity
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import tracing_runner
from azathoth.workflows import (
    WorkflowExperimentEvidenceRecorder,
    WorkflowGenerationError,
    WorkflowResultError,
    WorkflowScoringPolicy,
)

SENSITIVITY_WITHOUT_INPUT_MESSAGE: Final = (
    "--sensitivity labels the run's input; give --input or --input-file too."
)
"""What a run given a label but no input is refused with (ADR 0123)."""


def run_workflow(
    workflow_id: UUID,
    *,
    workflow_input: WorkflowRunInput | WorkflowInputFile | None = None,
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    sensitivity: Sensitivity | None = None,
) -> int:
    """Execute one configured workflow and persist its run as evidence.

    Completed runs are persisted whether they succeeded or failed, so configured
    execution history is inspectable alongside production invocation history.
    Runs that never start, because no candidate could be generated, leave no
    evidence.

    Supplied input starts the run with one canonical workflow input event, so
    the run can later become a benchmark case. Without input the run starts
    with an empty context.

    An input file is resolved before anything else happens (ADR 0096): its
    content is stored, and its provenance is recorded in the run's initial
    context. A file that cannot be resolved starts no run.

    The output format decides what the operator sees while and after the run
    executes. The command returns 0 when the run ends in a result record, and
    1 when it halted or did not produce its declared result.

    With tracing on, the run and its steps are traced (ADR 0100).

    A run started by a step of another run records the lineage it was given
    in `AZATHOTH_LINEAGE` (ADR 0104). Lineage that is not valid, or a run
    nested too deeply, raises before anything is resolved or recorded.

    The input is labelled with `sensitivity` when it is given (ADR 0123);
    a run given a label needs input.
    """

    return run_traced(
        lambda telemetry: _run_workflow(
            workflow_id,
            workflow_input=workflow_input,
            output=output,
            telemetry=telemetry,
            sensitivity=sensitivity,
        )
    )


def _run_workflow(
    workflow_id: UUID,
    *,
    workflow_input: WorkflowRunInput | WorkflowInputFile | None,
    output: WorkflowOutputFormat,
    telemetry: Telemetry,
    sensitivity: Sensitivity | None = None,
) -> int:
    """Execute one configured workflow, tracing it with the given telemetry."""

    lineage = parent_lineage(workflow_id)

    if sensitivity is not None and workflow_input is None:
        print(SENSITIVITY_WITHOUT_INPUT_MESSAGE, file=sys.stderr)

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    run_input: WorkflowRunInput | None

    if isinstance(workflow_input, WorkflowInputFile):
        run_input = _resolve_input_file(
            workflow_input,
            configuration,
        )

        if run_input is None:
            return 1
    else:
        run_input = workflow_input

    if run_input is not None and sensitivity is not None:
        run_input = replace(run_input, sensitivity=sensitivity)

    runtime = load_runtime(configuration)

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

    try:
        run = asyncio.run(
            execute_configured_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                context=configured_run_context(run_input, lineage=lineage),
                runner=tracing_runner(
                    telemetry,
                    observer=step_observer(
                        output,
                        writer,
                    ),
                    journal=repositories(configuration).run_journal,
                    leases=repositories(configuration).run_leases,
                    children=repositories(configuration).run_children,
                    content=repositories(configuration).tool_content,
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

    repositories(configuration).runs.save(run)

    #
    # Only a record names the declared result, so text never reads the
    # specification.
    #
    specification = (
        None if output is WorkflowOutputFormat.TEXT else runtime.workflows.get(workflow_id)
    )

    return report_configured_run(
        run,
        specification=specification,
        output=output,
        writer=writer,
    )


def _resolve_input_file(
    input_file: WorkflowInputFile,
    configuration: CliRuntimeConfiguration,
) -> WorkflowRunInput | None:
    """Resolve one input file into a run input, or report why it cannot be.

    The file's content is stored in the configured database.
    """

    try:
        resolved = resolve_input_file(
            input_file,
            store=repositories(configuration).content,
        )
    except (
        InputSourceError,
        InputResolutionError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )

        return None

    return WorkflowRunInput.from_resolved(resolved)


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
            production_repository=repositories(configuration).production_states,
            revision_repository=repositories(configuration).production_revisions,
            experiment_id=experiment_id,
            experiment_repository=repositories(configuration).experiments,
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
    payload: JsonValue | WorkflowInputFile,
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
    idempotency_key: str | None = None,
    sensitivity: Sensitivity | None = None,
) -> int:
    """Invoke one active production workflow.

    The payload is the JSON input, or an input file. A file is resolved before
    anything else happens (ADR 0096), and its provenance is recorded with the
    invocation; a file that cannot be resolved records no invocation.

    The output format decides what the caller sees while and after the
    invocation executes. The command returns 0 when the invocation succeeds
    and 1 when it fails.

    With tracing on, the invocation, its run and their steps are traced
    (ADR 0100).

    An invocation started by a step of another run records the lineage it
    was given in `AZATHOTH_LINEAGE` (ADR 0104). Lineage that is not valid, or
    an invocation nested too deeply, raises before anything is resolved or
    recorded.

    With an idempotency key, the invocation runs as `job run` runs a request
    under that key (ADR 0097): the same request again replays its result, or
    resumes it once nothing runs it (ADR 0105).

    The input is labelled with `sensitivity` when it is given, and the label
    is part of a keyed request (ADR 0123).
    """

    return run_traced(
        lambda telemetry: _invoke_workflow(
            workflow_id=workflow_id,
            payload=payload,
            output=output,
            telemetry=telemetry,
            idempotency_key=idempotency_key,
            sensitivity=sensitivity,
        )
    )


def _invoke_workflow(
    *,
    workflow_id: UUID,
    payload: JsonValue | WorkflowInputFile,
    output: WorkflowOutputFormat,
    telemetry: Telemetry,
    idempotency_key: str | None = None,
    sensitivity: Sensitivity | None = None,
) -> int:
    """Invoke one active production workflow, tracing it with the given telemetry."""

    lineage = parent_lineage(workflow_id)

    configuration = CliRuntimeConfiguration.from_environment()

    if idempotency_key is not None:
        return invoke_with_key(
            workflow_id=workflow_id,
            payload=payload,
            idempotency_key=idempotency_key,
            output=output,
            telemetry=telemetry,
            lineage=lineage,
            configuration=configuration,
            sensitivity=sensitivity,
        )

    invocation_input: JsonValue
    input_provenance: InputProvenance | None = None

    if isinstance(payload, WorkflowInputFile):
        resolved = _resolve_input_file(
            payload,
            configuration,
        )

        if resolved is None:
            return 1

        invocation_input = resolved.payload
        input_provenance = resolved.provenance
    else:
        invocation_input = payload

    runtime = load_runtime(configuration)

    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

    with traced_invocation(
        telemetry,
        workflow_id=workflow_id,
    ) as trace:
        result = asyncio.run(
            invoke_active_production_workflow(
                runtime=runtime,
                workflow_id=workflow_id,
                payload=invocation_input,
                invocation_repository=repositories(configuration).invocations,
                run_repository=repositories(configuration).runs,
                invocation_run_repository=repositories(configuration).invocation_runs,
                input_provenance=input_provenance,
                lineage=lineage,
                sensitivity=sensitivity,
                runner=tracing_runner(
                    telemetry,
                    observer=step_observer(
                        output,
                        writer,
                    ),
                    journal=repositories(configuration).run_journal,
                    leases=repositories(configuration).run_leases,
                    children=repositories(configuration).run_children,
                    content=repositories(configuration).tool_content,
                ),
            )
        )

        trace.record(result)

    return report_invocation_result(
        result,
        output=output,
        writer=writer,
    )


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
                    runs=repositories(configuration).runs,
                    evaluations=repositories(configuration).run_evaluations,
                    experiments=repositories(configuration).experiments,
                ),
                workflow_runner=case_runner(repositories(configuration)),
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
    "SENSITIVITY_WITHOUT_INPUT_MESSAGE",
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
