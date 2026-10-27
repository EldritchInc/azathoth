"""Tests proving the ticket-triage example's workflows, tool and benchmarks."""

import asyncio
import json
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
from azathoth.prompting import ContextPromptStrategy
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPricing,
    ModelResponse,
    Prompt,
)
from azathoth.tools import (
    ToolCatalog,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
    decode_tool_document,
    encode_tool_document,
)
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
    read_tool,
    read_workflow,
    run_with_input,
)
from tests.model_authorization import (
    generate_model_substitutions,
    generate_workflow_candidate,
)

TRIAGE_EXAMPLES = Path(__file__).parents[2] / "examples" / "ticket-triage"

FINALIZE_TOOL_DOCUMENT = TRIAGE_EXAMPLES / "tools" / "finalize-triage.json"

CLASSIFY_WORKFLOW_DOCUMENT = TRIAGE_EXAMPLES / "workflows" / "classify-ticket.json"

TRIAGE_WORKFLOW_DOCUMENT = TRIAGE_EXAMPLES / "workflows" / "triage-ticket.json"

CLASSIFY_BENCHMARK_DOCUMENT = TRIAGE_EXAMPLES / "benchmarks" / "classify-ticket.json"

TRIAGE_BENCHMARK_DOCUMENT = TRIAGE_EXAMPLES / "benchmarks" / "triage-ticket.json"

DRAFT_STEP_IDS = {
    "billing": UUID("f1000000-0000-4000-8000-000000000032"),
    "technical": UUID("f1000000-0000-4000-8000-000000000033"),
    "account": UUID("f1000000-0000-4000-8000-000000000034"),
    "other": UUID("f1000000-0000-4000-8000-000000000035"),
}

SPECIALISTS = {
    "billing": "a billing specialist",
    "technical": "a technical support engineer",
    "account": "an account specialist",
    "other": "a support generalist",
}

CATEGORIES = {
    "Charged twice": "billing",
    "Downgrade my plan": "billing",
    "Export fails": "technical",
    "Webhook never arrives": "technical",
    "Everything is down": "technical",
    "Locked out": "account",
    "Office hours": "other",
}

APPROVED_POLICY = '{"approved": true, "problems": []}'


class TriageModel:
    """Classify tickets by subject, draft as the prompted specialist, and review by script."""

    def __init__(
        self,
        *,
        provider: str = "scripted",
        model: str = "triage",
        policy: str = APPROVED_POLICY,
        urgency: str = "normal",
    ) -> None:
        self._provider = provider
        self._model = model
        self._policy = policy
        self._urgency = urgency
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return the scripted reply for the prompt."""

        self.prompts.append(prompt.text)

        reply = self._reply(prompt.text)

        return ModelResponse(
            text=reply,
            provider=self._provider,
            model=self._model,
            prompt_tokens=len(prompt.text.split()),
            completion_tokens=len(reply.split()),
            total_tokens=len(prompt.text.split()) + len(reply.split()),
            latency_ms=0,
            estimated_cost_usd=0.0,
        )

    def _reply(
        self,
        text: str,
    ) -> str:
        """Choose the reply for one prompt."""

        if text.startswith("You triage customer support tickets."):
            category = next(
                category for subject, category in CATEGORIES.items() if f'"{subject}"' in text
            )

            return json.dumps(
                {"category": category, "urgency": self._urgency, "summary": f"A {category} issue."}
            )

        if text.startswith("You review customer support replies"):
            return self._policy

        for category, role in SPECIALISTS.items():
            if text.startswith(f"You are {role} on the customer support team."):
                return f"Reply from the {category} specialist."

        raise AssertionError(f"No scripted reply for prompt: {text[:80]!r}")


def scripted_catalog(
    *models: tuple[str, float],
) -> ModelCatalog:
    """Return a catalog of scripted models with the given names and per-token prices."""

    return ModelCatalog(
        models=tuple(
            ModelMetadata(
                provider="scripted",
                model=name,
                display_name=name,
                context_window_tokens=32_768,
                pricing=ModelPricing(
                    input_usd_per_million_tokens=price,
                    output_usd_per_million_tokens=price,
                ),
            )
            for name, price in models
        )
    )


def read_benchmark(
    path: Path,
) -> BenchmarkDataset:
    """Decode one checked-in triage benchmark."""

    return decode_benchmark_document(path.read_text(encoding="utf-8"))


def classify_candidate(
    model: TriageModel,
) -> WorkflowCandidate:
    """Generate the classifier backed by the scripted model."""

    return generate_workflow_candidate(
        specification=read_workflow(CLASSIFY_WORKFLOW_DOCUMENT),
        catalog=scripted_catalog(("triage", 1.0)),
        registry=LanguageModelRegistry(models={"scripted/triage": model}),
    )


def triage_candidate(
    model: TriageModel,
) -> WorkflowCandidate:
    """Generate the triage workflow backed by the scripted model."""

    tool = read_tool(FINALIZE_TOOL_DOCUMENT)

    return generate_workflow_candidate(
        specification=read_workflow(TRIAGE_WORKFLOW_DOCUMENT),
        catalog=scripted_catalog(("triage", 1.0)),
        registry=LanguageModelRegistry(models={"scripted/triage": model}),
        tool_resolver=ToolResolver(ToolCatalog(definitions=(tool.definition,))),
        tool_implementation_resolver=ToolImplementationResolver(
            ToolImplementationCatalog(implementations=tool.implementations),
        ),
    )


def triage(
    model: TriageModel,
    subject: str,
) -> tuple[WorkflowRun, JsonValue]:
    """Triage one ticket, returning the run and its triage record."""

    workflow = read_workflow(TRIAGE_WORKFLOW_DOCUMENT)
    candidate = triage_candidate(model)

    run = run_with_input(
        candidate,
        {"subject": subject, "body": "Details.", "customer_tier": "standard"},
    )

    assert workflow.result is not None

    return run, workflow_result(run, workflow.result, steps=candidate.steps)


def draft_statuses(
    run: WorkflowRun,
) -> dict[str, WorkflowStepStatus]:
    """Return the status of each specialist draft step in a run, by category."""

    statuses = {step.step_id: step.status for step in run.steps}

    return {category: statuses[step_id] for category, step_id in DRAFT_STEP_IDS.items()}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(FINALIZE_TOOL_DOCUMENT, id="finalize-triage"),
        pytest.param(CLASSIFY_WORKFLOW_DOCUMENT, id="classify-ticket"),
        pytest.param(TRIAGE_WORKFLOW_DOCUMENT, id="triage-ticket"),
        pytest.param(CLASSIFY_BENCHMARK_DOCUMENT, id="classify-benchmark"),
        pytest.param(TRIAGE_BENCHMARK_DOCUMENT, id="triage-benchmark"),
    ],
)
def test_ticket_triage_documents_are_canonical(
    path: Path,
) -> None:
    encoded = path.read_text(encoding="utf-8").rstrip("\n")

    if path.parent.name == "tools":
        assert encode_tool_document(decode_tool_document(encoded)) == encoded
    elif path.parent.name == "workflows":
        assert encode_workflow_document(decode_workflow_document(encoded)) == encoded
    else:
        assert encode_benchmark_document(decode_benchmark_document(encoded)) == encoded


def test_both_workflows_share_one_classifier() -> None:
    classify = read_workflow(CLASSIFY_WORKFLOW_DOCUMENT).steps[0].specification
    triage_classify = read_workflow(TRIAGE_WORKFLOW_DOCUMENT).steps[0].specification

    assert classify == triage_classify


def test_classifier_is_benchmarked_exactly_and_triage_by_shape_and_meaning() -> None:
    assert read_benchmark(CLASSIFY_BENCHMARK_DOCUMENT).comparison_counts() == {
        OutcomeComparison.EXACT: 6,
    }
    assert read_benchmark(TRIAGE_BENCHMARK_DOCUMENT).comparison_counts() == {
        OutcomeComparison.SEMANTIC: 3,
        OutcomeComparison.SCHEMA: 1,
    }


def test_classifier_benchmark_runs_end_to_end() -> None:
    candidate = classify_candidate(TriageModel())

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            read_benchmark(CLASSIFY_BENCHMARK_DOCUMENT),
            every_case,
        )
    )

    assert (result.cases_run, result.cases_passed, result.run_failures) == (6, 6, 0)


@pytest.mark.parametrize(
    ("subject", "category"),
    [
        pytest.param("Charged twice", "billing", id="billing"),
        pytest.param("Export fails", "technical", id="technical"),
        pytest.param("Locked out", "account", id="account"),
        pytest.param("Office hours", "other", id="other"),
    ],
)
def test_each_ticket_is_drafted_by_exactly_one_specialist(
    subject: str,
    category: str,
) -> None:
    run, record = triage(TriageModel(), subject)

    assert draft_statuses(run) == {
        name: WorkflowStepStatus.EXECUTED if name == category else WorkflowStepStatus.SKIPPED
        for name in DRAFT_STEP_IDS
    }
    assert record == {
        "category": category,
        "urgency": "normal",
        "summary": f"A {category} issue.",
        "reply": f"Reply from the {category} specialist.",
        "approved": True,
        "problems": [],
        "needs_human": False,
    }


def test_reply_that_breaks_policy_is_flagged_for_a_person() -> None:
    model = TriageModel(
        policy='{"approved": false, "problems": ["Promises a refund."]}',
    )

    _, record = triage(model, "Charged twice")

    assert isinstance(record, dict)
    assert (record["approved"], record["problems"], record["needs_human"]) == (
        False,
        ["Promises a refund."],
        True,
    )


def test_urgent_ticket_is_flagged_for_a_person_even_when_approved() -> None:
    _, record = triage(TriageModel(urgency="high"), "Everything is down")

    assert isinstance(record, dict)
    assert (record["urgency"], record["approved"], record["needs_human"]) == ("high", True, True)


def test_policy_check_reads_the_specialist_reply() -> None:
    model = TriageModel()

    triage(model, "Locked out")

    (policy_prompt,) = (prompt for prompt in model.prompts if "review customer support" in prompt)

    assert "Reply from the account specialist." in policy_prompt
    assert '"subject":"Locked out"' in policy_prompt


def test_triage_record_satisfies_the_benchmark_schema() -> None:
    dataset = read_benchmark(TRIAGE_BENCHMARK_DOCUMENT)

    schema_only = BenchmarkDataset.model_validate(
        {
            **dict(dataset),
            "cases": tuple(
                case
                for case in dataset.cases
                if case.expected.comparison is OutcomeComparison.SCHEMA
            ),
        }
    )

    candidate = triage_candidate(TriageModel())

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(WorkflowBenchmarkRunner().run(schema_only, every_case))

    assert (result.cases_run, result.cases_passed) == (1, 1)


def test_classifier_is_offered_a_strictly_cheaper_model() -> None:
    workflow = read_workflow(CLASSIFY_WORKFLOW_DOCUMENT)
    catalog = scripted_catalog(("frontier", 10.0), ("compact", 1.0))
    registry = LanguageModelRegistry(
        models={
            "scripted/frontier": TriageModel(model="frontier"),
            "scripted/compact": TriageModel(model="compact"),
        }
    )

    frontier = catalog.get("scripted/frontier")

    assert frontier is not None

    candidate = generate_workflow_candidate(
        specification=workflow,
        catalog=ModelCatalog(models=(frontier,)),
        registry=registry,
    )

    substitutions = generate_model_substitutions(
        specification=workflow,
        candidate=candidate,
        catalog=catalog,
        registry=registry,
    )

    assert len(substitutions) == 1

    strategy = substitutions[0].steps[0].strategy

    assert isinstance(strategy, ContextPromptStrategy)
    assert strategy.model_binding is not None
    assert strategy.model_binding.identifier == "scripted/compact"
