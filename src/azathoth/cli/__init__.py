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
from azathoth.cli.workflows import (
    list_workflows,
    show_workflow,
)

__all__ = [
    "DATABASE_ENVIRONMENT_VARIABLE",
    "DEFAULT_DATABASE",
    "OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE",
    "CliRuntimeConfiguration",
    "build_parser",
    "list_workflows",
    "load_runtime",
    "main",
    "show_workflow",
]
