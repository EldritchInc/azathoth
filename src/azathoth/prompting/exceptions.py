"""Exceptions raised while rendering context-aware prompts."""


class PromptingError(Exception):
    """Base exception for prompt construction failures."""


class PromptBindingError(PromptingError):
    """Base exception for unresolved prompt bindings."""


class PromptBindingEventNotFoundError(PromptBindingError):
    """Raised when a binding's required context event is unavailable."""


class PromptBindingFieldNotFoundError(PromptBindingError):
    """Raised when a required field is absent from a context event."""