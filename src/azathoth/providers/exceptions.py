"""Exceptions raised by language model providers."""


class ModelExecutionError(RuntimeError):
    """Base exception raised when model execution cannot proceed."""


class UnsupportedModelRequestError(ModelExecutionError):
    """Raised when a model request requires unsupported execution behavior."""


class ModelDiscoveryError(RuntimeError):
    """Raised when provider model discovery cannot complete."""
