"""Azathoth's public service API, provisional until 1.4.0 (ADR 0120).

The command line, azathoth-mcp and the local UI all call Azathoth through
this one in-process, synchronous layer. Open an instance with `open`, and
read what it returns as the API's own frozen models.
"""

from azathoth.api.browsing import (
    LIMIT_MESSAGE,
    Benchmarks,
    Tools,
    Workflows,
)
from azathoth.api.errors import (
    CLOSED_MESSAGE,
    ApiError,
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
    InvalidArgumentError,
    NotFoundError,
    RevisionNotFoundError,
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
    BenchmarkDetail,
    BenchmarkSummary,
    InstanceDescription,
    Revision,
    ToolDetail,
    ToolSummary,
    WorkflowDetail,
    WorkflowSummary,
)

__all__ = [
    "API_STABILITY",
    "CLOSED_MESSAGE",
    "LIMIT_MESSAGE",
    "ApiError",
    "ApiModel",
    "ApiStability",
    "Azathoth",
    "Backend",
    "BenchmarkDetail",
    "BenchmarkSummary",
    "Benchmarks",
    "InstanceClosedError",
    "InstanceDescription",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
    "InvalidArgumentError",
    "NotFoundError",
    "Revision",
    "RevisionNotFoundError",
    "ToolDetail",
    "ToolSummary",
    "Tools",
    "WorkflowDetail",
    "WorkflowSummary",
    "Workflows",
    "open",
]
