"""Tests proving the workflow-writer example's workflow, tools and benchmark."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.prompting import ContextPromptStrategySpec, PromptOutputFormat
from azathoth.tools import (
    ToolDocument,
    ToolImplementation,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.tools.process import ProcessToolExecutor
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowRun,
    WorkflowStepStatus,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_revision_examples import (
    RoutingLanguageModel,
    generate_novel_candidate,
    read_tool,
    read_workflow,
    run_with_input,
)

WRITER_EXAMPLES = Path(__file__).parents[2] / "examples" / "workflow-writer"

VALIDATE_TOOL_DOCUMENT = WRITER_EXAMPLES / "tools" / "validate-workflow.json"

FINALIZE_TOOL_DOCUMENT = WRITER_EXAMPLES / "tools" / "finalize-workflow.json"

WRITE_WORKFLOW_DOCUMENT = WRITER_EXAMPLES / "workflows" / "write-workflow.json"

WRITE_BENCHMARK_DOCUMENT = WRITER_EXAMPLES / "benchmarks" / "write-workflow.json"

DRAFT_STEP_ID = UUID("a2000000-0000-4000-8000-000000000011")

VALIDATE_STEP_ID = UUID("a2000000-0000-4000-8000-000000000012")

REPAIR_STEP_ID = UUID("a2000000-0000-4000-8000-000000000013")

REVALIDATE_STEP_ID = UUID("a2000000-0000-4000-8000-000000000014")

FINALIZE_STEP_ID = UUID("a2000000-0000-4000-8000-000000000015")

DRAFT_MARKER = "Design a workflow for this request:"

REPAIR_MARKER = "was rejected by the workflow validator."

REQUEST = "Summarize the input text, then count the summary's words."


def runnable_validator() -> ToolDocument:
    """Return the validator running under this interpreter, which can import Azathoth.

    The checked-in tool runs "python", the interpreter of the active
    environment. The test interpreter is the one that has Azathoth installed.
    """

    document = read_tool(VALIDATE_TOOL_DOCUMENT)

    implementation = ToolImplementation.model_validate(
        {
            **document.implementations[0].model_dump(),
            "command": [sys.executable],
        }
    )

    return ToolDocument.model_validate(
        {
            **dict(document),
            "implementations": (implementation,),
        }
    )


def prompt_specification(
    step_id: UUID,
) -> ContextPromptStrategySpec:
    """Return one prompt step's specification from the write-workflow workflow."""

    (step,) = (step for step in read_workflow(WRITE_WORKFLOW_DOCUMENT).steps if step.id == step_id)

    assert isinstance(step.specification, ContextPromptStrategySpec)

    return step.specification


def draft_prompt_text() -> str:
    """Return the draft step's template text."""

    return prompt_specification(DRAFT_STEP_ID).template.text


def reference_workflow() -> dict[str, JsonValue]:
    """Return the complete workflow the draft prompt shows the model."""

    text = draft_prompt_text().replace("{{", "{").replace("}}", "}")

    start = text.index("\n{\n")
    end = text.index("\n}\n") + 2

    reference = json.loads(text[start:end])

    assert isinstance(reference, dict)

    return reference


def broken_reference() -> dict[str, JsonValue]:
    """Return the reference workflow with its second step's dependency removed."""

    broken = reference_workflow()

    steps = broken["steps"]
    assert isinstance(steps, list)

    second = steps[1]
    assert isinstance(second, dict)

    second["depends_on"] = []

    return broken


def validate(
    document: JsonValue,
) -> dict[str, JsonValue]:
    """Run the real validator tool on one document."""

    return asyncio.run(
        ProcessToolExecutor().execute(
            runnable_validator().implementations[0],
            {"document": document},
        )
    )


def writer_model(
    draft: JsonValue,
    repair: JsonValue | None = None,
) -> RoutingLanguageModel:
    """Script the draft reply and, when given, the repair reply."""

    routes = [(DRAFT_MARKER, json.dumps(draft))]

    if repair is not None:
        routes.append((REPAIR_MARKER, json.dumps(repair)))

    return RoutingLanguageModel(routes)


def writer_candidate(
    model: RoutingLanguageModel,
) -> WorkflowCandidate:
    """Generate the write-workflow candidate backed by the scripted model."""

    return generate_novel_candidate(
        read_workflow(WRITE_WORKFLOW_DOCUMENT),
        model,
        runnable_validator(),
        read_tool(FINALIZE_TOOL_DOCUMENT),
    )


def write(
    model: RoutingLanguageModel,
) -> tuple[WorkflowRun, JsonValue]:
    """Run the workflow writer and return its run and result."""

    candidate = writer_candidate(model)

    run = run_with_input(candidate, REQUEST)

    assert candidate.result is not None

    return run, workflow_result(run, candidate.result, steps=candidate.steps)


def statuses(
    run: WorkflowRun,
) -> dict[UUID, WorkflowStepStatus]:
    """Return each step's status by step ID."""

    return {step.step_id: step.status for step in run.steps}


def read_benchmark() -> BenchmarkDataset:
    """Decode the checked-in write-workflow benchmark."""

    return decode_benchmark_document(WRITE_BENCHMARK_DOCUMENT.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("path", "encode", "decode"),
    [
        pytest.param(
            VALIDATE_TOOL_DOCUMENT,
            encode_tool_document,
            decode_tool_document,
            id="validate-tool",
        ),
        pytest.param(
            FINALIZE_TOOL_DOCUMENT,
            encode_tool_document,
            decode_tool_document,
            id="finalize-tool",
        ),
        pytest.param(
            WRITE_WORKFLOW_DOCUMENT,
            encode_workflow_document,
            decode_workflow_document,
            id="write-workflow",
        ),
        pytest.param(
            WRITE_BENCHMARK_DOCUMENT,
            encode_benchmark_document,
            decode_benchmark_document,
            id="benchmark",
        ),
    ],
)
def test_workflow_writer_documents_are_canonical(
    path: Path,
    encode: object,
    decode: object,
) -> None:
    encoded = path.read_text(encoding="utf-8")

    assert callable(encode) and callable(decode)
    assert encode(decode(encoded)) == encoded.rstrip("\n")


def test_validator_runs_python_as_a_process() -> None:
    implementation = read_tool(VALIDATE_TOOL_DOCUMENT).implementations[0]

    assert implementation.runtime == "process"
    assert implementation.command == ("python",)


def test_draft_and_repair_reply_in_json() -> None:
    for step_id in (DRAFT_STEP_ID, REPAIR_STEP_ID):
        assert prompt_specification(step_id).output_format is PromptOutputFormat.JSON


def test_draft_prompt_shows_a_workflow_azathoth_accepts() -> None:
    reference = reference_workflow()

    decoded = decode_workflow_document(json.dumps(reference))

    assert json.loads(encode_workflow_document(decoded)) == reference


def test_validator_returns_the_canonical_form_of_a_valid_workflow() -> None:
    reference = reference_workflow()

    result = validate(reference)

    assert result == {"valid": True, "errors": "", "checked": reference}


def test_validator_reports_why_a_workflow_is_invalid() -> None:
    result = validate({"steps": []})

    assert result["valid"] is False
    assert result["checked"] == {"steps": []}
    assert result["errors"] == (
        "- metadata: Field required\n"
        "- steps: Tuple should have at least 1 item after validation, not 0"
    )


def test_validator_reports_errors_about_the_whole_workflow() -> None:
    result = validate(broken_reference())

    assert result["valid"] is False

    errors = result["errors"]
    assert isinstance(errors, str)
    assert errors.startswith("- document: ")
    assert "upstream workflow steps" in errors


def test_steps_run_draft_validate_repair_revalidate_finalize() -> None:
    layers = read_workflow(WRITE_WORKFLOW_DOCUMENT).execution_layers()

    assert [[step.id for step in layer] for layer in layers] == [
        [DRAFT_STEP_ID],
        [VALIDATE_STEP_ID],
        [REPAIR_STEP_ID],
        [REVALIDATE_STEP_ID],
        [FINALIZE_STEP_ID],
    ]


def test_valid_draft_is_not_repaired() -> None:
    model = writer_model(reference_workflow())

    run, result = write(model)

    assert result == {"valid": True, "errors": "", "workflow": reference_workflow()}

    assert statuses(run)[REPAIR_STEP_ID] is WorkflowStepStatus.SKIPPED
    assert statuses(run)[REVALIDATE_STEP_ID] is WorkflowStepStatus.SKIPPED
    assert model.prompts_containing(REPAIR_MARKER) == ()


def test_draft_prompt_carries_the_request() -> None:
    model = writer_model(reference_workflow())

    write(model)

    (prompt,) = model.prompts_containing(DRAFT_MARKER)

    assert REQUEST in prompt


def test_invalid_draft_is_repaired_from_the_validator_errors() -> None:
    model = writer_model(broken_reference(), repair=reference_workflow())

    run, result = write(model)

    assert result == {"valid": True, "errors": "", "workflow": reference_workflow()}

    assert statuses(run)[REPAIR_STEP_ID] is WorkflowStepStatus.EXECUTED
    assert statuses(run)[REVALIDATE_STEP_ID] is WorkflowStepStatus.EXECUTED


def test_repair_prompt_shows_the_request_draft_and_errors() -> None:
    model = writer_model(broken_reference(), repair=reference_workflow())

    write(model)

    (prompt,) = model.prompts_containing(REPAIR_MARKER)

    assert REQUEST in prompt
    assert json.dumps(broken_reference(), separators=(",", ":")) in prompt
    assert "upstream workflow steps" in prompt


def test_failed_repair_reports_the_revalidation_errors() -> None:
    model = writer_model(broken_reference(), repair={"steps": []})

    _, result = write(model)

    assert result == {
        "valid": False,
        "errors": (
            "- metadata: Field required\n"
            "- steps: Tuple should have at least 1 item after validation, not 0"
        ),
        "workflow": {"steps": []},
    }


def test_benchmark_checks_validity_by_schema_and_faithfulness_by_meaning() -> None:
    comparisons = [case.expected.comparison for case in read_benchmark().cases]

    assert comparisons.count(OutcomeComparison.SCHEMA) == 2
    assert comparisons.count(OutcomeComparison.SEMANTIC) == 2


def schema_cases() -> BenchmarkDataset:
    """Return only the benchmark's schema cases, which need no judge."""

    dataset = read_benchmark()

    return BenchmarkDataset.model_validate(
        {
            **dict(dataset),
            "cases": tuple(
                case
                for case in dataset.cases
                if case.expected.comparison is OutcomeComparison.SCHEMA
            ),
        }
    )


@pytest.mark.parametrize(
    ("draft", "repair", "passed"),
    [
        pytest.param("valid", None, 2, id="valid-draft"),
        pytest.param("broken", "valid", 2, id="repaired-draft"),
        pytest.param("broken", "empty", 0, id="unrepaired-draft"),
    ],
)
def test_benchmark_schema_passes_only_valid_workflows(
    draft: str,
    repair: str | None,
    passed: int,
) -> None:
    documents: dict[str, JsonValue] = {
        "valid": reference_workflow(),
        "broken": broken_reference(),
        "empty": {"steps": []},
    }

    candidate = writer_candidate(
        writer_model(
            documents[draft],
            repair=None if repair is None else documents[repair],
        )
    )

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(WorkflowBenchmarkRunner().run(schema_cases(), every_case))

    assert (result.cases_run, result.cases_passed) == (2, passed)
