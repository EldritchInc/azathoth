"""Command dispatch for the Azathoth CLI."""

from azathoth.cli.dispatching.benchmarks import (
    dispatch_benchmark_command,
)
from azathoth.cli.dispatching.goals import dispatch_goal_command
from azathoth.cli.dispatching.models import dispatch_model_command
from azathoth.cli.dispatching.tools import dispatch_tool_command
from azathoth.cli.dispatching.workflows import dispatch_workflow_command

__all__ = [
    "dispatch_benchmark_command",
    "dispatch_goal_command",
    "dispatch_model_command",
    "dispatch_tool_command",
    "dispatch_workflow_command",
]
