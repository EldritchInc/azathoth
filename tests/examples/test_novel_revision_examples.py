"""Tests proving the novel example's revise-chapter workflow, tools and benchmark."""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import JsonValue

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkDataset,
    OutcomeComparison,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.prompting import ContextPromptStrategySpec, PromptOutputFormat
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelResponse,
    Prompt,
)
from azathoth.tools import (
    ToolCatalog,
    ToolDocument,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
    decode_tool_document,
    encode_tool_document,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    create_workflow_input_event,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.model_authorization import generate_workflow_candidate

NOVEL_EXAMPLES = Path(__file__).parents[2] / "examples" / "novel"

STANDARD_TOOLS = Path(__file__).parents[2] / "src" / "azathoth" / "standard" / "tools"

SELECT_TOOL_DOCUMENT = STANDARD_TOOLS / "json-select.json"

PACK_TOOL_DOCUMENT = NOVEL_EXAMPLES / "tools" / "pack-revision.json"

REVISE_WORKFLOW_DOCUMENT = NOVEL_EXAMPLES / "workflows" / "revise-chapter.json"

REVISE_BENCHMARK_DOCUMENT = NOVEL_EXAMPLES / "benchmarks" / "revise-chapter.json"

MODEL_IDENTIFIER = "scripted/novelist"

APPLY_MARKER = "You are a novelist revising one chapter"

VERIFY_MARKER = "You are a meticulous editor checking whether a revision"

CONTEXT: JsonValue = {"title": "The Keeper", "premise": "A light keeps the sea asleep."}

CHAPTER = "Mara climbed the stairs. She was very afraid."

REQUESTS = ["Show Mara's fear through what she does."]

REVISED = "Mara climbed the stairs, gripping the rail until her knuckles whitened."


class RoutingLanguageModel:
    """Reply to each prompt with the reply of the first route whose marker it contains."""

    def __init__(
        self,
        routes: Sequence[tuple[str, str]],
    ) -> None:
        self._routes = tuple(routes)
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Record the prompt and return its routed reply."""

        self.prompts.append(prompt.text)

        for marker, reply in self._routes:
            if marker in prompt.text:
                return ModelResponse(
                    text=reply,
                    provider="scripted",
                    model="novelist",
                    prompt_tokens=len(prompt.text.split()),
                    completion_tokens=len(reply.split()),
                    total_tokens=len(prompt.text.split()) + len(reply.split()),
                    latency_ms=0,
                    estimated_cost_usd=0.0,
                )

        raise AssertionError(f"No scripted reply for prompt: {prompt.text[:80]!r}")

    def prompts_containing(
        self,
        marker: str,
    ) -> tuple[str, ...]:
        """Return every recorded prompt containing the marker."""

        return tuple(prompt for prompt in self.prompts if marker in prompt)


def read_tool(
    path: Path,
) -> ToolDocument:
    """Decode one checked-in novel tool document."""

    return decode_tool_document(path.read_text(encoding="utf-8"))


def read_workflow(
    path: Path,
) -> WorkflowSpecification:
    """Decode one checked-in novel workflow."""

    return decode_workflow_document(path.read_text(encoding="utf-8"))


def read_revise_benchmark() -> BenchmarkDataset:
    """Decode the checked-in revise-chapter benchmark."""

    return decode_benchmark_document(REVISE_BENCHMARK_DOCUMENT.read_text(encoding="utf-8"))


def generate_novel_candidate(
    workflow: WorkflowSpecification,
    model: RoutingLanguageModel,
    *tools: ToolDocument,
) -> WorkflowCandidate:
    """Generate an executable novel workflow backed by the scripted model and tools."""

    return generate_workflow_candidate(
        specification=workflow,
        catalog=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="scripted",
                    model="novelist",
                    display_name="Scripted Novelist",
                    context_window_tokens=1_000_000,
                ),
            ),
        ),
        registry=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: model,
            },
        ),
        tool_resolver=ToolResolver(
            ToolCatalog(definitions=tuple(tool.definition for tool in tools)),
        ),
        tool_implementation_resolver=ToolImplementationResolver(
            ToolImplementationCatalog(
                implementations=tuple(
                    implementation for tool in tools for implementation in tool.implementations
                ),
            )
        ),
    )


def run_with_input(
    candidate: WorkflowCandidate,
    workflow_input: JsonValue,
) -> WorkflowRun:
    """Run one candidate on one workflow input."""

    return asyncio.run(
        WorkflowRunner().run(
            workflow=candidate,
            context=Context(
                events=(
                    create_workflow_input_event(
                        workflow_input,
                        producer="examples-test",
                    ),
                )
            ),
        )
    )


def revise(
    model: RoutingLanguageModel,
    *,
    chapter: str = CHAPTER,
    requests: Sequence[str] = REQUESTS,
) -> JsonValue:
    """Run one revision pass and return the workflow's declared result."""

    workflow = read_workflow(REVISE_WORKFLOW_DOCUMENT)

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(SELECT_TOOL_DOCUMENT),
        read_tool(PACK_TOOL_DOCUMENT),
    )

    run = run_with_input(
        candidate,
        {
            "state": {"chapter": chapter, "requests": list(requests), "context": CONTEXT},
            "iteration": 1,
        },
    )

    assert workflow.result is not None

    return workflow_result(run, workflow.result, steps=candidate.steps)


def test_pack_revision_tool_example_is_canonical() -> None:
    encoded = PACK_TOOL_DOCUMENT.read_text(encoding="utf-8")

    assert encode_tool_document(decode_tool_document(encoded)) == encoded.rstrip("\n")


def test_revise_chapter_workflow_example_is_canonical() -> None:
    encoded = REVISE_WORKFLOW_DOCUMENT.read_text(encoding="utf-8")

    assert encode_workflow_document(decode_workflow_document(encoded)) == encoded.rstrip("\n")


def test_revise_chapter_benchmark_example_is_canonical() -> None:
    encoded = REVISE_BENCHMARK_DOCUMENT.read_text(encoding="utf-8")

    assert encode_benchmark_document(read_revise_benchmark()) == encoded.rstrip("\n")


def test_revise_chapter_applies_with_text_and_verifies_with_json() -> None:
    workflow = read_workflow(REVISE_WORKFLOW_DOCUMENT)

    formats = tuple(
        step.specification.output_format
        for step in workflow.steps
        if isinstance(step.specification, ContextPromptStrategySpec)
    )

    assert formats == (PromptOutputFormat.TEXT, PromptOutputFormat.JSON)
    assert isinstance(workflow.result, WorkflowNamedValueReference)
    assert workflow.result.name == "next"


def test_revision_pass_is_done_when_every_request_is_met() -> None:
    model = RoutingLanguageModel(
        (
            (APPLY_MARKER, REVISED),
            (VERIFY_MARKER, '```json\n{"unmet": []}\n```'),
        )
    )

    assert revise(model) == {
        "state": {"chapter": REVISED, "requests": [], "context": CONTEXT},
        "done": True,
        "item": 0,
    }


def test_revision_pass_carries_unmet_requests_into_the_next_pass() -> None:
    model = RoutingLanguageModel(
        (
            (APPLY_MARKER, REVISED),
            (VERIFY_MARKER, '{"unmet": ["Also show it in her breathing."]}'),
        )
    )

    assert revise(model) == {
        "state": {
            "chapter": REVISED,
            "requests": ["Also show it in her breathing."],
            "context": CONTEXT,
        },
        "done": False,
        "item": 1,
    }


def test_revision_prompts_carry_the_chapter_requests_and_revision() -> None:
    model = RoutingLanguageModel(
        (
            (APPLY_MARKER, REVISED),
            (VERIFY_MARKER, '{"unmet": []}'),
        )
    )

    revise(model)

    (apply_prompt,) = model.prompts_containing(APPLY_MARKER)
    (verify_prompt,) = model.prompts_containing(VERIFY_MARKER)

    assert CHAPTER in apply_prompt
    assert json.dumps(REQUESTS, ensure_ascii=False, separators=(",", ":")) in apply_prompt
    assert '"title":"The Keeper"' in apply_prompt
    assert REVISED in verify_prompt
    assert '{"unmet": []}' in verify_prompt


def test_revise_chapter_benchmark_judges_semantically_in_the_loop_protocol() -> None:
    dataset = read_revise_benchmark()

    assert len(dataset.cases) == 2

    for case in dataset.cases:
        assert case.expected.comparison is OutcomeComparison.SEMANTIC
        assert isinstance(case.input, dict)
        assert case.input["iteration"] == 1
        assert isinstance(case.input["state"], dict)
        assert set(case.input["state"]) == {"chapter", "requests", "context"}


def test_revise_chapter_runs_on_every_benchmark_input() -> None:
    workflow = read_workflow(REVISE_WORKFLOW_DOCUMENT)

    model = RoutingLanguageModel(
        (
            (APPLY_MARKER, REVISED),
            (VERIFY_MARKER, '{"unmet": []}'),
        )
    )

    candidate = generate_novel_candidate(
        workflow,
        model,
        read_tool(SELECT_TOOL_DOCUMENT),
        read_tool(PACK_TOOL_DOCUMENT),
    )

    assert workflow.result is not None

    for case in read_revise_benchmark().cases:
        run = run_with_input(candidate, case.input)

        result = workflow_result(run, workflow.result, steps=candidate.steps)

        assert isinstance(result, dict)
        assert result["done"] is True
