"""Tests for generating tool-backed workflow candidates."""

from uuid import UUID

import pytest

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolCatalog,
    ToolDefinition,
    ToolImplementation,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolInputSchema,
    ToolOutputSchema,
    ToolRequirement,
    ToolResolver,
    ToolStrategy,
)
from azathoth.workflows import (
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowGenerationError,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
TOOL_ID = UUID("33333333-3333-3333-3333-333333333333")
IMPLEMENTATION_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_definition() -> ToolDefinition:
    """Create a deterministic word-count capability."""

    return ToolDefinition(
        id=TOOL_ID,
        name="word_count",
        description="Count words in supplied text.",
        version="1.0.0",
        input_schema=ToolInputSchema(
            json_schema={
                "type": "object",
            },
        ),
        output_schema=ToolOutputSchema(
            json_schema={
                "type": "object",
            },
        ),
    )


def create_implementation(
    *,
    runtime: str = "python",
) -> ToolImplementation:
    """Create a deterministic word-count implementation."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        version="1.0.0",
        runtime=runtime,
        source=("def run():\n    return {'word_count': 3}\n"),
    )


def create_specification(
    *,
    runtime: str | None = "python",
) -> WorkflowSpecification:
    """Create a workflow containing one tool-backed step."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Tool workflow",
            description="Execute a durable tool.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=ToolStepSpecification(
                    requirement=ToolRequirement(
                        name="word_count",
                        version="1.0.0",
                        runtime=runtime,
                    ),
                ),
            ),
        ),
    )


def create_tool_resolver() -> ToolResolver:
    """Create a resolver containing the word-count capability."""

    return ToolResolver(
        ToolCatalog(
            definitions=(create_definition(),),
        )
    )


def create_implementation_resolver(
    implementation: ToolImplementation | None = None,
) -> ToolImplementationResolver:
    """Create a resolver containing one executable implementation."""

    implementations = () if implementation is None else (implementation,)

    return ToolImplementationResolver(
        ToolImplementationCatalog(
            implementations=implementations,
        )
    )


def generate_candidate(
    specification: WorkflowSpecification,
    *,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> WorkflowCandidate:
    """Generate a candidate without configured language models."""

    return generate_workflow_candidate(
        specification=specification,
        catalog=ModelCatalog(),
        registry=LanguageModelRegistry(
            models={},
        ),
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
    )


def test_tool_step_resolves_to_tool_strategy() -> None:
    candidate = generate_candidate(
        create_specification(),
        tool_resolver=create_tool_resolver(),
        tool_implementation_resolver=create_implementation_resolver(
            create_implementation(),
        ),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ToolStrategy,
    )
    assert strategy.metadata.id == TOOL_ID
    assert strategy.metadata.name == "word_count"
    assert strategy.metadata.version == "1.0.0"


def test_tool_step_preserves_resolved_implementation() -> None:
    implementation = create_implementation()

    candidate = generate_candidate(
        create_specification(),
        tool_resolver=create_tool_resolver(),
        tool_implementation_resolver=create_implementation_resolver(
            implementation,
        ),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ToolStrategy,
    )
    assert strategy.implementation == implementation


def test_tool_step_requires_tool_resolver() -> None:
    with pytest.raises(
        WorkflowGenerationError,
        match="require a tool resolver",
    ):
        generate_candidate(
            create_specification(),
            tool_implementation_resolver=create_implementation_resolver(
                create_implementation(),
            ),
        )


def test_tool_step_requires_implementation_resolver() -> None:
    with pytest.raises(
        WorkflowGenerationError,
        match="require a tool implementation resolver",
    ):
        generate_candidate(
            create_specification(),
            tool_resolver=create_tool_resolver(),
        )


def test_tool_step_rejects_unmatched_requirement() -> None:
    specification = create_specification()

    with pytest.raises(
        WorkflowGenerationError,
        match="No tool definition satisfies requirement",
    ):
        generate_candidate(
            specification,
            tool_resolver=ToolResolver(
                ToolCatalog(),
            ),
            tool_implementation_resolver=create_implementation_resolver(
                create_implementation(),
            ),
        )


def test_tool_step_rejects_missing_implementation() -> None:
    with pytest.raises(
        WorkflowGenerationError,
        match="No executable tool implementation satisfies requirement",
    ):
        generate_candidate(
            create_specification(),
            tool_resolver=create_tool_resolver(),
            tool_implementation_resolver=create_implementation_resolver(),
        )


def test_tool_step_applies_runtime_requirement() -> None:
    with pytest.raises(
        WorkflowGenerationError,
        match="No executable tool implementation satisfies requirement",
    ):
        generate_candidate(
            create_specification(
                runtime="python",
            ),
            tool_resolver=create_tool_resolver(),
            tool_implementation_resolver=create_implementation_resolver(
                create_implementation(
                    runtime="javascript",
                ),
            ),
        )


def test_tool_step_uses_first_matching_implementation() -> None:
    first = create_implementation()

    second = first.model_copy(
        update={
            "id": UUID("55555555-5555-5555-5555-555555555555"),
            "version": "2.0.0",
        },
    )

    candidate = generate_candidate(
        create_specification(),
        tool_resolver=create_tool_resolver(),
        tool_implementation_resolver=ToolImplementationResolver(
            ToolImplementationCatalog(
                implementations=(
                    first,
                    second,
                ),
            )
        ),
    )

    strategy = candidate.steps[0].strategy

    assert isinstance(
        strategy,
        ToolStrategy,
    )
    assert strategy.implementation == first
