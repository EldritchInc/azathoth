"""Exceptions raised by tool execution."""


class ToolExecutionError(RuntimeError):
    """Base exception raised when tool execution fails."""


class UnsupportedToolRuntimeError(ToolExecutionError):
    """Raised when an executor cannot execute an implementation runtime."""


class ToolEntrypointError(ToolExecutionError):
    """Raised when a tool implementation has an invalid entrypoint."""
