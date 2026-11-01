"""Durable tool capabilities, execution, resolution, and verification."""

from azathoth.tools.catalog import ToolCatalog
from azathoth.tools.catalog_loader import ToolCatalogLoader
from azathoth.tools.definition import (
    ToolDefinition,
    ToolInputSchema,
    ToolOutputSchema,
)
from azathoth.tools.dispatch import (
    RuntimeToolExecutor,
    default_tool_executors,
    supported_tool_runtimes,
    unsupported_runtime_message,
)
from azathoth.tools.document import (
    ToolDocument,
    ToolDocumentError,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.tools.environment import (
    POSIX_BASE_ENVIRONMENT,
    WINDOWS_BASE_ENVIRONMENT,
    process_tool_environment,
)
from azathoth.tools.exceptions import (
    ToolEntrypointError,
    ToolExecutionError,
    UnsupportedToolRuntimeError,
)
from azathoth.tools.execution import (
    PYTHON_TOOL_RUNTIME,
    PythonToolExecutor,
)
from azathoth.tools.implementation import (
    ENVIRONMENT_GRANT_PATTERN,
    ENVIRONMENT_PREFIX_WILDCARD,
    PROCESS_TOOL_RUNTIME,
    ToolImplementation,
)
from azathoth.tools.implementation_catalog import ToolImplementationCatalog
from azathoth.tools.implementation_resolution import (
    ToolImplementationResolver,
)
from azathoth.tools.matching import ToolMatcher
from azathoth.tools.memory_repository import (
    InMemoryToolRepository,
    require_tool_repository,
)
from azathoth.tools.process import (
    PROCESS_STDERR_TAIL_CHARACTERS,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    ProcessToolExecutor,
)
from azathoth.tools.protocols import ToolExecutor
from azathoth.tools.repository import ToolRepository
from azathoth.tools.requirements import (
    ToolRequirement,
    ToolRequirementMatch,
    ToolRequirements,
)
from azathoth.tools.resolution import ToolResolver
from azathoth.tools.revision import (
    ToolDocumentRevision,
    earliest_identical_tool_revision,
)
from azathoth.tools.sqlite_repository import SQLiteToolRepository
from azathoth.tools.strategy import ToolStrategy
from azathoth.tools.testing import ToolTestCase
from azathoth.tools.verification import ToolTestResult, ToolVerification
from azathoth.tools.verifier import ToolVerifier

__all__ = [
    "InMemoryToolRepository",
    "PROCESS_STDERR_TAIL_CHARACTERS",
    "ENVIRONMENT_GRANT_PATTERN",
    "ENVIRONMENT_PREFIX_WILDCARD",
    "POSIX_BASE_ENVIRONMENT",
    "PROCESS_TOOL_RUNTIME",
    "PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE",
    "PYTHON_TOOL_RUNTIME",
    "WINDOWS_BASE_ENVIRONMENT",
    "ProcessToolExecutor",
    "PythonToolExecutor",
    "RuntimeToolExecutor",
    "SQLiteToolRepository",
    "ToolCatalog",
    "ToolCatalogLoader",
    "ToolDefinition",
    "ToolDocument",
    "ToolDocumentError",
    "ToolDocumentRevision",
    "ToolEntrypointError",
    "ToolExecutionError",
    "ToolExecutor",
    "ToolImplementation",
    "ToolImplementationCatalog",
    "ToolImplementationResolver",
    "ToolInputSchema",
    "ToolMatcher",
    "ToolOutputSchema",
    "ToolRepository",
    "ToolRequirement",
    "ToolRequirementMatch",
    "ToolRequirements",
    "ToolResolver",
    "ToolStrategy",
    "ToolTestCase",
    "ToolTestResult",
    "ToolVerification",
    "ToolVerifier",
    "UnsupportedToolRuntimeError",
    "decode_tool_document",
    "default_tool_executors",
    "earliest_identical_tool_revision",
    "encode_tool_document",
    "process_tool_environment",
    "require_tool_repository",
    "supported_tool_runtimes",
    "unsupported_runtime_message",
]
