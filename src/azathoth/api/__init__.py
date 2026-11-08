"""Azathoth's public service API, provisional until 1.4.0 (ADR 0120).

The command line, azathoth-mcp and the local UI all call Azathoth through
this one in-process, synchronous layer. Open an instance with `open`, and
read what it returns as the API's own frozen models.
"""

from azathoth.api.errors import (
    CLOSED_MESSAGE,
    ApiError,
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
)
from azathoth.api.instance import (
    Azathoth,
    open,
)
from azathoth.api.models import (
    API_STABILITY,
    ApiModel,
    ApiStability,
    Backend,
    InstanceDescription,
)

__all__ = [
    "API_STABILITY",
    "CLOSED_MESSAGE",
    "ApiError",
    "ApiModel",
    "ApiStability",
    "Azathoth",
    "Backend",
    "InstanceClosedError",
    "InstanceDescription",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
    "open",
]
