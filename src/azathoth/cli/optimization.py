"""Application services for optimizing configured workflows.

`workflow optimize` optimizes through the same function the service API's
`optimization.optimize` calls (ADR 0131), so the two cannot come to
optimize differently. It lives in the API, and is named here as the command
line always named it.
"""

from azathoth.api.optimization import optimize_configured_workflow

__all__ = [
    "optimize_configured_workflow",
]
