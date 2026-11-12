"""Command-line application for Azathoth."""

import sys
from argparse import Namespace
from collections.abc import Sequence
from typing import cast

from azathoth.cli.annotations import (
    export_invocation_annotations,
    export_run_annotations,
)
from azathoth.cli.benchmark_cases import add_benchmark_case
from azathoth.cli.benchmarks import (
    compare_benchmarks,
    export_benchmark,
    import_benchmark,
    list_benchmark_cases,
    list_benchmark_executions,
    list_benchmark_history,
    list_benchmarks,
    run_benchmark,
    show_benchmark,
    show_benchmark_case,
    show_benchmark_execution,
)
from azathoth.cli.dispatching import (
    dispatch_benchmark_command,
    dispatch_experiment_command,
    dispatch_goal_command,
    dispatch_invocation_command,
    dispatch_job_command,
    dispatch_judge_command,
    dispatch_model_command,
    dispatch_remote_command,
    dispatch_run_command,
    dispatch_tool_command,
    dispatch_worker_command,
    dispatch_workflow_command,
)
from azathoth.cli.experiments import (
    list_workflow_experiments,
    show_experiment,
)
from azathoth.cli.goals import (
    import_goal,
    list_goals,
    show_goal,
)
from azathoth.cli.initialization import initialize_database
from azathoth.cli.jobs import run_job_request
from azathoth.cli.judges import (
    add_judge,
    list_judges,
    remove_judge,
)
from azathoth.cli.mcp_tools import tool_from_mcp
from azathoth.cli.models import (
    authorize_model,
    deauthorize_model,
    list_models,
    list_portfolio_models,
    model_policy,
    show_model,
)
from azathoth.cli.parsing import (
    BENCHMARK_COMMAND,
    COMMAND_ATTRIBUTE,
    EXPERIMENT_COMMAND,
    GOAL_COMMAND,
    INIT_COMMAND,
    INVOCATION_COMMAND,
    JOB_COMMAND,
    JUDGE_COMMAND,
    MODEL_COMMAND,
    REMOTE_COMMAND,
    RUN_COMMAND,
    TOOL_COMMAND,
    WORKER_COMMAND,
    WORKFLOW_COMMAND,
    build_parser,
)
from azathoth.cli.production_inspection import (
    list_workflow_invocations,
    list_workflow_revisions,
    show_invocation,
    show_workflow_production,
)
from azathoth.cli.remote import (
    add_remote,
    create_remote_token,
    list_remote_tokens,
    list_remotes,
    pull_from_remote,
    push_to_remote,
    remove_remote,
    revoke_remote_token,
    serve_remote,
)
from azathoth.cli.resumption import resume_invocation, resume_run
from azathoth.cli.runs import (
    list_run_children,
    list_workflow_runs,
    record_run_feedback,
    show_run,
)
from azathoth.cli.streams import use_utf8_streams
from azathoth.cli.termination import (
    INTERRUPTED_MESSAGE,
    INTERRUPTED_STATUS,
    TERMINATED_MESSAGE,
    TERMINATED_STATUS,
    CommandTerminated,
    terminating_on_sigterm,
)
from azathoth.cli.tool_verification import verify_tool
from azathoth.cli.tools import (
    export_tool,
    import_tool,
    install_standard_tools,
    list_tool_history,
    list_tool_implementations,
    list_tool_test_cases,
    list_tool_versions,
    list_tools,
    show_tool,
    show_tool_implementation,
    show_tool_test_case,
)
from azathoth.cli.usage import (
    model_usage,
    tool_usage,
)
from azathoth.cli.worker import check_worker_health, run_worker
from azathoth.cli.workflows import (
    export_workflow,
    import_workflow,
    invoke_workflow,
    list_workflow_history,
    list_workflows,
    optimize_workflow,
    promote_workflow,
    run_workflow,
    show_workflow,
)
from azathoth.context import LineageError, WorkflowDepthError
from azathoth.inputs import ContentStoreError, InputUnavailableError
from azathoth.persistence import DatabaseSchemaError, DatabaseUnavailableError
from azathoth.persistence.repositories import close_postgres_databases
from azathoth.providers import (
    BedrockConfigurationError,
    BedrockUnavailableError,
    ModelDiscoveryError,
)
from azathoth.worker import WorkerError
from azathoth.workflows import RunJournalError, RunLeaseError, RunResumeError


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the Azathoth command-line application.

    Output is always written as UTF-8, whatever the platform's code page.
    A PostgreSQL database that cannot be used here, Bedrock configuration
    that cannot be used, a provider whose models cannot be discovered,
    lineage that is not valid, a child nested too deeply, and a run that
    could not be journaled, lost its lease or cannot be resumed are each
    reported on stderr in one line, and the command exits with status 1.

    A command stopped by Ctrl-C prints `Interrupted.` and exits with 130;
    one stopped by SIGTERM prints `Terminated.` and exits with 143. Either
    unwinds first, so a run it was executing releases its lease (ADR 0105).
    `worker run` handles its own signals, and drains on the first of them
    (ADR 0107). A worker without its extra, whose queue cannot be used, or
    whose heartbeat cannot be written is reported in one line, with status 1.
    """

    use_utf8_streams(
        sys.stdout,
        sys.stderr,
    )

    parser = build_parser()

    arguments = parser.parse_args(argv)

    try:
        with terminating_on_sigterm():
            result = _dispatch(arguments)
    except KeyboardInterrupt:
        print(
            INTERRUPTED_MESSAGE,
            file=sys.stderr,
        )

        return INTERRUPTED_STATUS
    except CommandTerminated:
        print(
            TERMINATED_MESSAGE,
            file=sys.stderr,
        )

        return TERMINATED_STATUS
    except (
        DatabaseUnavailableError,
        DatabaseSchemaError,
        BedrockUnavailableError,
        BedrockConfigurationError,
        ModelDiscoveryError,
        LineageError,
        WorkflowDepthError,
        RunJournalError,
        RunLeaseError,
        RunResumeError,
        WorkerError,
        InputUnavailableError,
        ContentStoreError,
    ) as exc:
        #
        # A PostgreSQL database that cannot be used here, because the
        # postgres extra is missing or its schema is not this Azathoth's,
        # stops any command before it changes anything (ADR 0102). So does
        # a provider that is on but cannot be used: Bedrock without its
        # extra, its region or a usable pricing document, or any provider
        # whose models cannot be discovered (ADR 0103). So does a child
        # whose lineage is not valid, or that would be nested too deeply
        # (ADR 0104). So does a run that could not be journaled, lost its
        # lease, or cannot be resumed (ADR 0105): it stays unfinished. So
        # does a worker without its extra, whose queue cannot be used, or
        # whose heartbeat cannot be written (ADR 0107), or that cannot
        # reach S3 for an input it is allowed to read (ADR 0108). So does
        # a content store that is misconfigured or refuses (ADR 0108).
        #
        print(
            str(exc),
            file=sys.stderr,
        )

        return 1
    finally:
        close_postgres_databases()

    if result is not None:
        return result

    parser.print_help()

    return 0


def _dispatch(
    arguments: Namespace,
) -> int | None:
    """Dispatch parsed CLI arguments to a command-family dispatcher."""

    command = cast(
        str | None,
        getattr(
            arguments,
            COMMAND_ATTRIBUTE,
            None,
        ),
    )

    if command == INIT_COMMAND:
        return initialize_database()

    if command == BENCHMARK_COMMAND:
        return dispatch_benchmark_command(
            arguments,
            add_benchmark_case=add_benchmark_case,
            compare_benchmarks=compare_benchmarks,
            export_benchmark=export_benchmark,
            import_benchmark=import_benchmark,
            list_benchmark_cases=list_benchmark_cases,
            list_benchmark_executions=list_benchmark_executions,
            list_benchmark_history=list_benchmark_history,
            list_benchmarks=list_benchmarks,
            run_benchmark=run_benchmark,
            show_benchmark=show_benchmark,
            show_benchmark_case=show_benchmark_case,
            show_benchmark_execution=show_benchmark_execution,
        )

    if command == GOAL_COMMAND:
        return dispatch_goal_command(
            arguments,
            import_goal=import_goal,
            list_goals=list_goals,
            show_goal=show_goal,
        )

    if command == WORKFLOW_COMMAND:
        return dispatch_workflow_command(
            arguments,
            export_workflow=export_workflow,
            import_workflow=import_workflow,
            invoke_workflow=invoke_workflow,
            list_workflow_experiments=list_workflow_experiments,
            list_workflow_history=list_workflow_history,
            list_workflow_invocations=list_workflow_invocations,
            list_workflow_revisions=list_workflow_revisions,
            list_workflow_runs=list_workflow_runs,
            list_workflows=list_workflows,
            optimize_workflow=optimize_workflow,
            promote_workflow=promote_workflow,
            run_workflow=run_workflow,
            show_workflow=show_workflow,
            show_workflow_production=show_workflow_production,
        )

    if command == RUN_COMMAND:
        return dispatch_run_command(
            arguments,
            record_run_feedback=record_run_feedback,
            show_run=show_run,
            resume_run=resume_run,
            list_run_children=list_run_children,
            export_run_annotations=export_run_annotations,
        )

    if command == EXPERIMENT_COMMAND:
        return dispatch_experiment_command(
            arguments,
            show_experiment=show_experiment,
        )

    if command == INVOCATION_COMMAND:
        return dispatch_invocation_command(
            arguments,
            show_invocation=show_invocation,
            resume_invocation=resume_invocation,
            export_invocation_annotations=export_invocation_annotations,
        )

    if command == JOB_COMMAND:
        return dispatch_job_command(
            arguments,
            run_job_request=run_job_request,
        )

    if command == WORKER_COMMAND:
        return dispatch_worker_command(
            arguments,
            run_worker=run_worker,
            check_worker_health=check_worker_health,
        )

    if command == MODEL_COMMAND:
        return dispatch_model_command(
            arguments,
            authorize_model=authorize_model,
            deauthorize_model=deauthorize_model,
            list_models=list_models,
            list_portfolio_models=list_portfolio_models,
            model_policy=model_policy,
            model_usage=model_usage,
            show_model=show_model,
        )

    if command == JUDGE_COMMAND:
        return dispatch_judge_command(
            arguments,
            add_judge=add_judge,
            list_judges=list_judges,
            remove_judge=remove_judge,
        )

    if command == REMOTE_COMMAND:
        return dispatch_remote_command(
            arguments,
            create_remote_token=create_remote_token,
            list_remote_tokens=list_remote_tokens,
            revoke_remote_token=revoke_remote_token,
            serve_remote=serve_remote,
            push_to_remote=push_to_remote,
            pull_from_remote=pull_from_remote,
            add_remote=add_remote,
            list_remotes=list_remotes,
            remove_remote=remove_remote,
        )

    if command == TOOL_COMMAND:
        return dispatch_tool_command(
            arguments,
            export_tool=export_tool,
            import_tool=import_tool,
            install_standard_tools=install_standard_tools,
            list_tool_history=list_tool_history,
            list_tool_implementations=list_tool_implementations,
            list_tool_test_cases=list_tool_test_cases,
            list_tool_versions=list_tool_versions,
            list_tools=list_tools,
            show_tool=show_tool,
            show_tool_implementation=show_tool_implementation,
            show_tool_test_case=show_tool_test_case,
            tool_usage=tool_usage,
            verify_tool=verify_tool,
            tool_from_mcp=tool_from_mcp,
        )

    return None
