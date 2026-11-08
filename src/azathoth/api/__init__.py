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
from azathoth.api.catalog import (
    Models,
    Portfolio,
)
from azathoth.api.errors import (
    CLOSED_MESSAGE,
    ApiError,
    ConflictError,
    InstanceClosedError,
    InstanceNotFoundError,
    InstanceSchemaError,
    InstanceUnavailableError,
    InvalidArgumentError,
    ModelInUseError,
    NotFoundError,
    ProviderConfigurationError,
    ProviderUnavailableError,
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
    ModelSummary,
    PortfolioEntry,
    PortfolioRemoval,
    ProductionDependent,
    ProductionStepUsage,
    Revision,
    ToolDetail,
    ToolSummary,
    WorkflowDetail,
    WorkflowSummary,
)
from azathoth.api.providers import (
    BEDROCK_VARIABLES,
    OPENROUTER_API_KEY_VARIABLE,
    ProviderSettings,
)

__all__ = [
    "API_STABILITY",
    "BEDROCK_VARIABLES",
    "CLOSED_MESSAGE",
    "LIMIT_MESSAGE",
    "OPENROUTER_API_KEY_VARIABLE",
    "ApiError",
    "ApiModel",
    "ApiStability",
    "Azathoth",
    "Backend",
    "BenchmarkDetail",
    "BenchmarkSummary",
    "Benchmarks",
    "ConflictError",
    "InstanceClosedError",
    "InstanceDescription",
    "InstanceNotFoundError",
    "InstanceSchemaError",
    "InstanceUnavailableError",
    "InvalidArgumentError",
    "ModelInUseError",
    "ModelSummary",
    "Models",
    "NotFoundError",
    "Portfolio",
    "PortfolioEntry",
    "PortfolioRemoval",
    "ProductionDependent",
    "ProductionStepUsage",
    "ProviderConfigurationError",
    "ProviderSettings",
    "ProviderUnavailableError",
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
