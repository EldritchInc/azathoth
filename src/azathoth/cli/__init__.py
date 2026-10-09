"""Azathoth command-line interface."""

from azathoth.cli.application import main
from azathoth.cli.benchmark_execution import (
    compare_configured_benchmarks,
    execute_configured_benchmark,
)
from azathoth.cli.benchmarks import (
    compare_benchmarks,
    import_benchmark,
    list_benchmark_cases,
    list_benchmarks,
    run_benchmark,
    show_benchmark,
    show_benchmark_case,
)
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import (
    DATABASE_ENVIRONMENT_VARIABLE,
    DEFAULT_DATABASE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
    CliRuntimeConfiguration,
)
from azathoth.cli.execution import execute_configured_workflow
from azathoth.cli.experiments import (
    list_workflow_experiments,
    show_experiment,
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
from azathoth.cli.optimization import optimize_configured_workflow
from azathoth.cli.parsing import build_parser
from azathoth.cli.production import invoke_active_production_workflow
from azathoth.cli.promotion import promote_configured_workflow
from azathoth.cli.rendering import (
    render_model_usage_report,
    render_production_invocation_result,
    render_tool_usage_report,
    render_workflow_benchmark_ranking,
    render_workflow_benchmark_result,
    render_workflow_experiment,
    render_workflow_experiment_summaries,
    render_workflow_optimization_session,
    render_workflow_promotion,
    render_workflow_run,
    render_workflow_run_feedback,
    render_workflow_run_summaries,
)
from azathoth.cli.runs import (
    list_workflow_runs,
    record_run_feedback,
    show_run,
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
from azathoth.cli.usage import (
    model_usage,
    tool_usage,
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

__all__ = [
    "DATABASE_ENVIRONMENT_VARIABLE",
    "DEFAULT_DATABASE",
    "OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE",
    "CliRuntimeConfiguration",
    "authorize_model",
    "build_parser",
    "compare_benchmarks",
    "compare_configured_benchmarks",
    "deauthorize_model",
    "execute_configured_benchmark",
    "execute_configured_workflow",
    "import_benchmark",
    "import_goal",
    "import_tool",
    "import_workflow",
    "invoke_active_production_workflow",
    "invoke_workflow",
    "list_benchmark_cases",
    "list_benchmarks",
    "list_goals",
    "list_models",
    "list_portfolio_models",
    "list_tool_implementations",
    "list_tool_test_cases",
    "list_tool_versions",
    "list_tools",
    "list_workflow_experiments",
    "list_workflow_runs",
    "list_workflows",
    "load_runtime",
    "main",
    "model_usage",
    "optimize_configured_workflow",
    "optimize_workflow",
    "promote_configured_workflow",
    "promote_workflow",
    "record_run_feedback",
    "render_model_usage_report",
    "render_production_invocation_result",
    "render_tool_usage_report",
    "render_workflow_benchmark_ranking",
    "render_workflow_benchmark_result",
    "render_workflow_experiment",
    "render_workflow_experiment_summaries",
    "render_workflow_optimization_session",
    "render_workflow_promotion",
    "render_workflow_run",
    "render_workflow_run_feedback",
    "render_workflow_run_summaries",
    "run_benchmark",
    "run_workflow",
    "show_model",
    "show_run",
    "show_benchmark",
    "show_benchmark_case",
    "show_experiment",
    "show_goal",
    "show_tool",
    "show_tool_implementation",
    "show_tool_test_case",
    "show_workflow",
    "tool_usage",
    "verify_tool",
]
