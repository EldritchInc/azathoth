"""Command-line application for Azathoth."""

from argparse import Namespace
from collections.abc import Sequence
from typing import cast

from azathoth.cli.benchmarks import (
    compare_benchmarks,
    import_benchmark,
    list_benchmark_cases,
    list_benchmarks,
    run_benchmark,
    show_benchmark,
    show_benchmark_case,
)
from azathoth.cli.dispatching import (
    dispatch_benchmark_command,
    dispatch_goal_command,
    dispatch_model_command,
    dispatch_tool_command,
    dispatch_workflow_command,
)
from azathoth.cli.goals import (
    import_goal,
    list_goals,
    show_goal,
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
    GOAL_COMMAND,
    MODEL_COMMAND,
    TOOL_COMMAND,
    WORKFLOW_COMMAND,
    build_parser,
)
from azathoth.cli.tool_verification import verify_tool
from azathoth.cli.tools import (
    import_tool,
    list_tool_implementations,
    list_tool_test_cases,
    list_tool_versions,
    list_tools,
    show_tool,
    show_tool_implementation,
    show_tool_test_case,
)
from azathoth.cli.workflows import (
    import_workflow,
    invoke_workflow,
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
            compare_benchmarks=compare_benchmarks,
            import_benchmark=import_benchmark,
            list_benchmark_cases=list_benchmark_cases,
            list_benchmarks=list_benchmarks,
            run_benchmark=run_benchmark,
            show_benchmark=show_benchmark,
            show_benchmark_case=show_benchmark_case,
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
            import_workflow=import_workflow,
            invoke_workflow=invoke_workflow,
            list_workflows=list_workflows,
            optimize_workflow=optimize_workflow,
            promote_workflow=promote_workflow,
            run_workflow=run_workflow,
            show_workflow=show_workflow,
        )

    if command == MODEL_COMMAND:
        return dispatch_model_command(
            arguments,
            authorize_model=authorize_model,
            deauthorize_model=deauthorize_model,
            list_models=list_models,
            list_portfolio_models=list_portfolio_models,
            show_model=show_model,
        )

    if command == TOOL_COMMAND:
        return dispatch_tool_command(
            arguments,
            import_tool=import_tool,
            list_tool_implementations=list_tool_implementations,
            list_tool_test_cases=list_tool_test_cases,
            list_tool_versions=list_tool_versions,
            list_tools=list_tools,
            show_tool=show_tool,
            show_tool_implementation=show_tool_implementation,
            show_tool_test_case=show_tool_test_case,
            verify_tool=verify_tool,
        )

    return None
