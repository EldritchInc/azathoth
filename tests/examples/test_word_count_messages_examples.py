"""Tests proving the word-count step-messages example is valid and streams as documented."""

import asyncio
import io
import json
from pathlib import Path
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.rendering import workflow_run_record
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.context import Context
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolCatalog,
    ToolDocument,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowFailurePolicy,
    WorkflowNamedValueReference,
    WorkflowRunner,
    WorkflowSpecification,
    create_workflow_input_event,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.examples.test_redundant_word_count_examples import (
    MISSING_INTERPRETER,
    PROCESS_TOOL_DOCUMENT,
    PYTHON_TOOL_DOCUMENT,
    read_tool,
)
from tests.model_authorization import generate_workflow_candidate

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "word-count-messages.json"

WORKFLOW_ID = UUID("a1000000-0000-4000-8000-000000000002")

PROCESS_STEP_ID = UUID("a1000000-0000-4000-8000-000000000021")

PYTHON_STEP_ID = UUID("a1000000-0000-4000-8000-000000000022")

PROCESS_MESSAGE = "Counting words with the process tool"

PYTHON_MESSAGE = "Counting words with the Python tool"

TEXT = "the old ones wait"


def read_workflow() -> WorkflowSpecification:
    """Decode the checked-in step-messages workflow."""

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


def stream(
    candidate: WorkflowCandidate,
) -> list[dict[str, JsonValue]]:
    """Run the candidate on the example text, returning its JSON Lines records."""

    output = io.StringIO()

    writer = JsonLinesOutputWriter(output)

    run = asyncio.run(
        WorkflowRunner(
            observer=writer,
        ).run_recording_failures(
            candidate,
            Context(
                events=(
                    create_workflow_input_event(
                        TEXT,
                        producer="examples-test",
                    ),
                )
            ),
        )
    )

    writer.write(
        workflow_run_record(
            run,
            result=candidate.result,
            steps=candidate.steps,
        )
    )

    records = [json.loads(line) for line in output.getvalue().splitlines()]

    assert records[-1].get("run_id") == str(run.id)

    return records


def without_run_id(
    record: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Return a record without its run identifier."""

    return {key: value for key, value in record.items() if key != "run_id"}


def test_word_count_messages_example_is_canonical() -> None:
    encoded = WORKFLOW_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert encode_workflow_document(read_workflow()) == encoded.rstrip("\n")


def test_word_count_messages_example_announces_both_steps() -> None:
    workflow = read_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert workflow.result == WorkflowNamedValueReference(
        name="count",
    )
    assert tuple((step.id, step.message, step.emit_values) for step in workflow.steps) == (
        (PROCESS_STEP_ID, PROCESS_MESSAGE, True),
        (PYTHON_STEP_ID, PYTHON_MESSAGE, False),
    )
    assert all(step.failure_policy is WorkflowFailurePolicy.CONTINUE for step in workflow.steps)


def test_word_count_messages_example_streams_messages_values_and_result() -> None:
    records = stream(
        generate_candidate(
            read_tool(PROCESS_TOOL_DOCUMENT),
            read_tool(PYTHON_TOOL_DOCUMENT),
        )
    )

    assert [without_run_id(record) for record in records] == [
        {
            "type": "step",
            "step_id": str(PROCESS_STEP_ID),
            "message": PROCESS_MESSAGE,
        },
        {
            "type": "step",
            "step_id": str(PYTHON_STEP_ID),
            "message": PYTHON_MESSAGE,
        },
        {
            "type": "output",
            "step_id": str(PROCESS_STEP_ID),
            "values": {
                "count": 4,
            },
        },
        {
            "type": "result",
            "value": 4,
        },
    ]


def test_word_count_messages_example_falls_back_without_emitting_the_failed_step() -> None:
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

    records = stream(
        generate_candidate(
            broken_tool,
            read_tool(PYTHON_TOOL_DOCUMENT),
        )
    )

    assert [without_run_id(record) for record in records] == [
        {
            "type": "step",
            "step_id": str(PROCESS_STEP_ID),
            "message": PROCESS_MESSAGE,
        },
        {
            "type": "step",
            "step_id": str(PYTHON_STEP_ID),
            "message": PYTHON_MESSAGE,
        },
        {
            "type": "result",
            "value": 4,
        },
    ]
