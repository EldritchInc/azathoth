"""Exceptions raised by language model provider execution."""


class ModelExecutionError(RuntimeError):
    """Base exception raised when model execution cannot proceed."""


class UnsupportedModelRequestError(ModelExecutionError):
    """Raised when a model request requires unsupported execution behavior."""
