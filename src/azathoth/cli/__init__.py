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

__all__ = [
    "DATABASE_ENVIRONMENT_VARIABLE",
    "DEFAULT_DATABASE",
    "OPENROUTER_API_KEY_ENVIRONMENT_VARIABLE",
    "CliRuntimeConfiguration",
    "build_parser",
    "load_runtime",
    "main",
]
