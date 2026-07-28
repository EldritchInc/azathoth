"""Exceptions raised by executable Azathoth strategies."""


class StrategyError(Exception):
    """Base exception for strategy execution failures."""


class RequiredEventNotFoundError(StrategyError):
    """Raised when a strategy cannot find a required context event."""


class RequiredFieldNotFoundError(StrategyError):
    """Raised when a required field is absent from an event payload."""
