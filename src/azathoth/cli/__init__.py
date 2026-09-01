"""Azathoth command-line interface."""

from azathoth.cli.application import (
    build_parser,
    main,
)
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import (
    DATABASE_ENVIRONMENT_VARIABLE,
    DEFAULT_DATABASE,
    OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE,
    CliRuntimeConfiguration,
)
from azathoth.cli.execution import execute_configured_workflow
from azathoth.cli.models import (
    authorize_model,
    list_models,
    list_portfolio_models,
    show_model,
)
from azathoth.cli.rendering import render_workflow_run
from azathoth.cli.workflows import (
    import_workflow,
    list_workflows,
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
    "execute_configured_workflow",
    "import_workflow",
    "list_models",
    "list_portfolio_models",
    "list_workflows",
    "load_runtime",
    "main",
    "render_workflow_run",
    "run_workflow",
    "show_model",
    "show_workflow",
]
