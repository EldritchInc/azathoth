"""Command-line application for Azathoth."""

from argparse import Namespace
from collections.abc import Sequence
from typing import cast

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
    dispatch_judge_command,
    dispatch_model_command,
    dispatch_run_command,
    dispatch_tool_command,
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
from azathoth.cli.judges import (
    add_judge,
    list_judges,
    remove_judge,
)
from azathoth.cli.models import (
    authorize_model,
    deauthorize_model,
    list_models,
    list_portfolio_models,
    show_model,
)
from azathoth.cli.parsing import (
    BENCHMARK_COMMAND,
    COMMAND_ATTRIBUTE,
    EXPERIMENT_COMMAND,
    GOAL_COMMAND,
    INVOCATION_COMMAND,
    JUDGE_COMMAND,
    MODEL_COMMAND,
    RUN_COMMAND,
    TOOL_COMMAND,
    WORKFLOW_COMMAND,
    build_parser,
)
from azathoth.cli.production_inspection import (
    list_workflow_invocations,
    list_workflow_revisions,
    show_invocation,
    show_workflow_production,
)
from azathoth.cli.runs import (
    list_workflow_runs,
    record_run_feedback,
    show_run,
)
from azathoth.cli.tool_verification import verify_tool
from azathoth.cli.tools import (
    export_tool,
    import_tool,
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


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the Azathoth command-line application."""

    parser = build_parser()

    arguments = parser.parse_args(argv)

    result = _dispatch(arguments)

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
        )

    if command == MODEL_COMMAND:
        return dispatch_model_command(
            arguments,
            authorize_model=authorize_model,
            deauthorize_model=deauthorize_model,
            list_models=list_models,
            list_portfolio_models=list_portfolio_models,
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

    if command == TOOL_COMMAND:
        return dispatch_tool_command(
            arguments,
            export_tool=export_tool,
            import_tool=import_tool,
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
        )

    return None
