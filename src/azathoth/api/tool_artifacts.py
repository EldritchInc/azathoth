"""A tool's current definition, implementations and test cases as the service API shows them.

Importing a tool document makes its artifacts current (ADR 0122); `tool
show`, `tool implementations`, `tool implementation-show`, `tool
test-cases` and `tool test-case-show` read those, and so do the calls
these views serve (ADR 0140), so a tool a remote holds is shown as one
here is.
"""

import shlex
from uuid import UUID

from azathoth.api.models import (
    ToolDefinitionDetail,
    ToolImplementationDetail,
    ToolImplementationSummary,
    ToolMcpBinding,
    ToolTestCaseDetail,
    ToolTestCaseSummary,
)
from azathoth.tools import ToolDefinition, ToolImplementation, ToolTestCase


def definition_detail(
    definition: ToolDefinition,
) -> ToolDefinitionDetail:
    """Return the API's view of one tool version's current definition."""

    return ToolDefinitionDetail(
        id=definition.id,
        name=definition.name,
        version=definition.version,
        description=definition.description,
        input_schema=dict(definition.input_schema.json_schema),
        output_schema=dict(definition.output_schema.json_schema),
        command=f"azathoth tool show {definition.id} --version {shlex.quote(definition.version)}",
    )


def implementation_summary(
    implementation: ToolImplementation,
) -> ToolImplementationSummary:
    """Return what a list of a tool version's implementations shows of one."""

    return ToolImplementationSummary(
        implementation_id=implementation.id,
        tool_id=implementation.tool_id,
        tool_version=implementation.tool_version,
        version=implementation.version,
        runtime=implementation.runtime,
        command=f"azathoth tool implementation-show {implementation.id}",
    )


def implementation_detail(
    implementation: ToolImplementation,
) -> ToolImplementationDetail:
    """Return one implementation with what it runs."""

    binding = implementation.mcp

    return ToolImplementationDetail(
        **implementation_summary(implementation).model_dump(),
        entrypoint=implementation.entrypoint if binding is None else None,
        argv=implementation.command,
        timeout_seconds=implementation.timeout_seconds,
        environment=implementation.environment,
        mcp=(
            None
            if binding is None
            else ToolMcpBinding(
                server=binding.server.describe(),
                tool=binding.tool,
                schema_digest=binding.schema_digest,
                authorization=binding.credentials.authorization,
            )
        ),
        source=implementation.source,
    )


def verification_case_summary(
    test_case: ToolTestCase,
) -> ToolTestCaseSummary:
    """Return what a list of a tool's verification cases shows of one."""

    return ToolTestCaseSummary(
        test_case_id=test_case.id,
        tool_id=test_case.tool_id,
        name=test_case.name,
        command=f"azathoth tool test-case-show {test_case.id}",
    )


def verification_case_detail(
    test_case: ToolTestCase,
) -> ToolTestCaseDetail:
    """Return one verification case with its inputs and expected output."""

    return ToolTestCaseDetail(
        **verification_case_summary(test_case).model_dump(),
        description=test_case.description,
        inputs=dict(test_case.inputs),
        expected_output=dict(test_case.expected_output),
    )


def implementation_not_found_message(
    implementation_id: UUID,
) -> str:
    """Return what an implementation that is not kept is refused with."""

    return f"Tool implementation {implementation_id} is not configured."


def verification_case_not_found_message(
    test_case_id: UUID,
) -> str:
    """Return what a verification case that is not kept is refused with."""

    return f"Tool test case {test_case_id} is not configured."


__all__ = [
    "definition_detail",
    "implementation_detail",
    "implementation_not_found_message",
    "implementation_summary",
    "verification_case_detail",
    "verification_case_not_found_message",
    "verification_case_summary",
]
