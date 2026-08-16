"""End-to-end tests for deterministic implementation resolution."""

import asyncio
from uuid import UUID

from azathoth.tools import (
    PythonToolExecutor,
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolResolver,
    ToolTestCase,
    ToolVerifier,
)

TOOL_ID = UUID("11111111-1111-1111-1111-111111111111")

PYTHON_IMPLEMENTATION_ID = UUID("22222222-2222-2222-2222-222222222222")

JAVASCRIPT_IMPLEMENTATION_ID = UUID("33333333-3333-3333-3333-333333333333")

TEST_CASE_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_definition() -> ToolDefinition:
    """Create a deterministic tool definition."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count whitespace-delimited words.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                    },
                },
                "required": [
                    "text",
                ],
            },
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                    },
                },
                "required": [
                    "count",
                ],
            },
        ),
    )


def create_catalog() -> ToolCatalog:
    """Create a deterministic definition catalog."""

    return ToolCatalog(
        definitions=(create_definition(),),
    )


def create_python_implementation() -> ToolImplementation:
    """Create a Python implementation."""

    return ToolImplementation(
        id=PYTHON_IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="python",
        entrypoint="run",
        source=("def run(text: str) -> dict[str, int]:\n    return {'count': len(text.split())}\n"),
    )


def create_javascript_implementation() -> ToolImplementation:
    """Create a placeholder JavaScript implementation."""

    return ToolImplementation(
        id=JAVASCRIPT_IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime="javascript",
        entrypoint="run",
        source="// placeholder",
    )


def create_implementation_catalog() -> ToolImplementationCatalog:
    """Create an implementation catalog."""

    return ToolImplementationCatalog(
        implementations=(
            create_python_implementation(),
            create_javascript_implementation(),
        ),
    )


def create_test_case() -> ToolTestCase:
    """Create a deterministic verification test."""

    return ToolTestCase(
        id=TEST_CASE_ID,
        tool_id=TOOL_ID,
        name="counts words",
        description="Verify deterministic counting.",
        inputs={
            "text": "hello world",
        },
        expected_output={
            "count": 2,
        },
    )


def test_complete_capability_lifecycle() -> None:
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    definitions = ToolResolver(
        create_catalog(),
    ).resolve(
        requirement,
    )

    assert len(definitions) == 1

    implementations = ToolImplementationResolver(
        create_implementation_catalog(),
    ).resolve_for_requirement(
        definitions[0],
        requirement,
    )

    assert len(implementations) == 1

    implementation = implementations[0]

    assert implementation.runtime == "python"
    assert implementation.id == PYTHON_IMPLEMENTATION_ID

    verification = asyncio.run(
        ToolVerifier(
            PythonToolExecutor(),
        ).verify(
            implementation,
            (create_test_case(),),
        )
    )

    assert verification.passed
    assert verification.pass_rate == 1.0
    assert verification.passed_count == 1
    assert verification.failed_count == 0


def test_runtime_constraint_selects_python_only() -> None:
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    implementations = ToolImplementationResolver(
        create_implementation_catalog(),
    ).resolve_for_requirement(
        create_definition(),
        requirement,
    )

    assert tuple(implementation.runtime for implementation in implementations) == ("python",)


def test_runtime_constraint_survives_json_round_trip() -> None:
    requirement = ToolRequirement(
        name="word_count",
        runtime="python",
    )

    restored = ToolRequirement.model_validate_json(
        requirement.model_dump_json(),
    )

    implementations = ToolImplementationResolver(
        create_implementation_catalog(),
    ).resolve_for_requirement(
        create_definition(),
        restored,
    )

    assert restored == requirement

    assert tuple(implementation.runtime for implementation in implementations) == ("python",)
