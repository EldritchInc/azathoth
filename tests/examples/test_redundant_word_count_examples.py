"""Tests proving the redundant word-count examples are valid and runnable."""

import asyncio
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    RuntimeToolExecutor,
    ToolCatalog,
    ToolDocument,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
    ToolVerifier,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowFailurePolicy,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepStatus,
    create_workflow_input_event,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.model_authorization import generate_workflow_candidate

PROJECT_ROOT = Path(__file__).parents[2]

PROCESS_TOOL_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count-process.json"

PYTHON_TOOL_DOCUMENT = PROJECT_ROOT / "examples" / "tools" / "word-count.json"

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "redundant-word-count.json"

WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000001")

PROCESS_STEP_ID = UUID("a1000000-0000-4000-8000-000000000011")

PYTHON_STEP_ID = UUID("a1000000-0000-4000-8000-000000000012")

MISSING_INTERPRETER = ("azathoth-no-such-interpreter",)


def read_tool(
    path: Path,
) -> ToolDocument:
    """Decode one checked-in tool document."""

    return decode_tool_document(
        path.read_text(
            encoding="utf-8",
        )
    )


def read_workflow() -> WorkflowSpecification:
    """Decode the checked-in redundant word-count workflow."""

    return decode_workflow_document(
        WORKFLOW_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def generate_candidate(
    *tools: ToolDocument,
) -> WorkflowCandidate:
    """Generate the example workflow against the given tool documents."""

    return generate_workflow_candidate(
        specification=read_workflow(),
        catalog=ModelCatalog(),
        registry=LanguageModelRegistry(
            models={},
        ),
        tool_resolver=ToolResolver(
            ToolCatalog(
                definitions=tuple(tool.definition for tool in tools),
            )
        ),
        tool_implementation_resolver=ToolImplementationResolver(
            ToolImplementationCatalog(
                implementations=tuple(
                    implementation for tool in tools for implementation in tool.implementations
                ),
            )
        ),
    )


def run_candidate(
    candidate: WorkflowCandidate,
    text: str,
) -> WorkflowRun:
    """Run one candidate on one workflow input."""

    return asyncio.run(
        WorkflowRunner().run(
            workflow=candidate,
            context=Context(
                events=(
                    create_workflow_input_event(
                        text,
                        producer="examples-test",
                    ),
                )
            ),
        )
    )


def test_process_tool_example_is_canonical() -> None:
    encoded = PROCESS_TOOL_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")


def test_process_tool_example_declares_a_process_implementation() -> None:
    implementation = read_tool(PROCESS_TOOL_DOCUMENT).implementations[0]

    assert implementation.runtime == PROCESS_TOOL_RUNTIME
    assert implementation.command == ("python3",)
    assert implementation.timeout_seconds == 30.0


def test_process_tool_example_passes_its_test_cases() -> None:
    document = read_tool(PROCESS_TOOL_DOCUMENT)

    verification = asyncio.run(
        ToolVerifier(
            RuntimeToolExecutor(),
        ).verify(
            document.implementations[0],
            document.test_cases,
        )
    )

    assert verification.passed


def test_redundant_word_count_workflow_example_is_canonical() -> None:
    encoded = WORKFLOW_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_workflow_document(read_workflow()) == encoded.rstrip("\n")


def test_redundant_word_count_workflow_names_its_result() -> None:
    workflow = read_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert workflow.result == WorkflowNamedValueReference(
        name="count",
    )


def test_redundant_word_count_producers_share_one_tolerant_layer() -> None:
    workflow = read_workflow()

    layers = workflow.execution_layers()

    assert len(layers) == 1
    assert tuple(step.id for step in layers[0]) == (
        PROCESS_STEP_ID,
        PYTHON_STEP_ID,
    )

    assert all(step.failure_policy is WorkflowFailurePolicy.CONTINUE for step in workflow.steps)


def test_redundant_word_count_answers_from_the_process_tool() -> None:
    candidate = generate_candidate(
        read_tool(PROCESS_TOOL_DOCUMENT),
        read_tool(PYTHON_TOOL_DOCUMENT),
    )

    run = run_candidate(
        candidate,
        "the old ones wait",
    )

    assert all(step.status is WorkflowStepStatus.EXECUTED for step in run.steps)

    assert candidate.result is not None

    assert (
        workflow_result(
            run,
            candidate.result,
            steps=candidate.steps,
        )
        == 4
    )

    assert tuple(value.producer_step_id for value in run.values_named("count")) == (
        PROCESS_STEP_ID,
        PYTHON_STEP_ID,
    )


def test_redundant_word_count_falls_back_when_the_process_tool_fails() -> None:
    process_tool = read_tool(PROCESS_TOOL_DOCUMENT)

    broken_tool = process_tool.model_copy(
        update={
            "implementations": (
                process_tool.implementations[0].model_copy(
                    update={
                        "command": MISSING_INTERPRETER,
                    }
                ),
            ),
        }
    )

    candidate = generate_candidate(
        broken_tool,
        read_tool(PYTHON_TOOL_DOCUMENT),
    )

    run = run_candidate(
        candidate,
        "the old ones wait",
    )

    assert tuple(step.status for step in run.steps) == (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.EXECUTED,
    )

    assert candidate.result is not None

    assert (
        workflow_result(
            run,
            candidate.result,
            steps=candidate.steps,
        )
        == 4
    )
