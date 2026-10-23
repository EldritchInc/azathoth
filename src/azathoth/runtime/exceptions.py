"""Exceptions raised by Azathoth runtime composition."""


class AzathothRuntimeError(Exception):
    """Base exception raised by Azathoth runtime composition."""


class WorkflowNotConfiguredError(AzathothRuntimeError):
    """Raised when a requested workflow is absent from the runtime."""


class JudgeUnavailableError(AzathothRuntimeError):
    """Raised when semantic judging is needed but a judge cannot be used."""
