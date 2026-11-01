"""Tests proving the ticket-triage example's escalating classifier (ADR 0098)."""

import asyncio
import json
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import BenchmarkCase
from azathoth.prompting import ContextPromptStrategySpec
from azathoth.providers import (
    LanguageModelRegistry,
    ModelResponse,
    Prompt,
)
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowConditionOperator,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowStepStatus,
    WorkflowValueReference,
    decode_workflow_document,
    encode_workflow_document,
    workflow_result,
)
from tests.examples.test_novel_revision_examples import read_workflow, run_with_input
from tests.examples.test_ticket_triage_examples import (
    CATEGORIES,
    CLASSIFY_BENCHMARK_DOCUMENT,
    CLASSIFY_WORKFLOW_DOCUMENT,
    TRIAGE_EXAMPLES,
    read_benchmark,
    scripted_catalog,
)
from tests.model_authorization import generate_workflow_candidate

ESCALATING_WORKFLOW_DOCUMENT = TRIAGE_EXAMPLES / "workflows" / "classify-ticket-escalating.json"

ESCALATE_STEP_ID = UUID("f1000000-0000-4000-8000-000000000072")

CLASSIFY_STEP_ID = UUID("f1000000-0000-4000-8000-000000000071")

CHEAP_PROMPT = "You triage customer support tickets."

STRONG_PROMPT = "You are a senior support lead."

UNSURE_SUBJECT = "Downgrade my plan"

CHEAP_ANSWERS: dict[str, tuple[str, JsonValue]] = {
    "Charged twice": ("billing", 0.97),
    "Downgrade my plan": ("account", 0.55),
    "Export fails": ("technical", 0.93),
    "Webhook never arrives": ("technical", 0.86),
    "Locked out": ("account", 0.95),
    "Office hours": ("other", 0.9),
}
"""What the cheap model answers: right and sure, except about a plan change."""


class ClassifierModel:
    """Answer classification prompts by subject; the cheap prompts as scripted."""

    def __init__(
        self,
        model: str,
        *,
        cheap_answers: dict[str, tuple[str, JsonValue]] | None = None,
    ) -> None:
        self._model = model
        self._cheap_answers = CHEAP_ANSWERS if cheap_answers is None else cheap_answers
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return the scripted reply for the prompt."""

        self.prompts.append(prompt.text)

        reply = json.dumps(self._reply(prompt.text))

        return ModelResponse(
            text=reply,
            provider="scripted",
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
    ) -> dict[str, JsonValue]:
        """Choose the reply for one prompt."""

        subject = next(subject for subject in CATEGORIES if f'"{subject}"' in text)

        if text.startswith(STRONG_PROMPT):
            category = CATEGORIES[subject]

            return {"category": category, "urgency": "normal", "summary": f"A {category} issue."}

        assert text.startswith(CHEAP_PROMPT), text[:80]

        category, confidence = self._cheap_answers[subject]

        reply: dict[str, JsonValue] = {
            "category": category,
            "urgency": "normal",
            "summary": f"A {category} issue.",
        }

        if "confidence" in text:
            reply["confidence"] = confidence

        return reply


class Models:
    """A frontier model first in the portfolio, and a compact model cheap enough to classify."""

    def __init__(
        self,
        *,
        cheap_answers: dict[str, tuple[str, JsonValue]] | None = None,
    ) -> None:
        self.frontier = ClassifierModel("frontier", cheap_answers=cheap_answers)
        self.compact = ClassifierModel("compact", cheap_answers=cheap_answers)
        self.catalog = scripted_catalog(("frontier", 10.0), ("compact", 0.25))
        self.registry = LanguageModelRegistry(
            models={
                "scripted/frontier": self.frontier,
                "scripted/compact": self.compact,
            }
        )


def escalating_candidate(
    models: Models,
) -> WorkflowCandidate:
    """Generate the escalating classifier against the scripted models."""

    return generate_workflow_candidate(
        specification=read_workflow(ESCALATING_WORKFLOW_DOCUMENT),
        catalog=models.catalog,
        registry=models.registry,
    )


def classify(
    models: Models,
    subject: str,
) -> tuple[WorkflowRun, JsonValue]:
    """Classify one ticket, returning the run and the workflow's result."""

    workflow = read_workflow(ESCALATING_WORKFLOW_DOCUMENT)
    candidate = escalating_candidate(models)

    run = run_with_input(
        candidate,
        {"subject": subject, "body": "Details.", "customer_tier": "standard"},
    )

    assert workflow.result is not None

    return run, workflow_result(run, workflow.result, steps=candidate.steps)


def step(
    run: WorkflowRun,
    step_id: UUID,
) -> WorkflowStepRun:
    """Return one step's run."""

    return next(step for step in run.steps if step.step_id == step_id)


def model_of(
    step_run: WorkflowStepRun,
) -> str | None:
    """Return the model one executed step ran on."""

    assert step_run.execution is not None
    assert step_run.execution.metrics is not None

    return step_run.execution.metrics.model


# The document


def test_the_escalating_classifier_is_canonical() -> None:
    encoded = ESCALATING_WORKFLOW_DOCUMENT.read_text(encoding="utf-8").rstrip("\n")

    assert encode_workflow_document(decode_workflow_document(encoded)) == encoded


def test_the_escalation_step_is_declared_first_and_backs_up_the_classifier() -> None:
    workflow = read_workflow(ESCALATING_WORKFLOW_DOCUMENT)

    escalate, classifier = workflow.steps

    assert (escalate.id, classifier.id) == (ESCALATE_STEP_ID, CLASSIFY_STEP_ID)
    assert escalate.depends_on == (CLASSIFY_STEP_ID,)
    assert {output.name for output in escalate.outputs} == {"category", "urgency", "summary"}
    assert {output.name for output in escalate.outputs} < {
        output.name for output in classifier.outputs
    }
    assert workflow.result == WorkflowNamedValueReference(name="category")


def test_the_classifier_reports_its_confidence_and_escalation_waits_on_it() -> None:
    escalate, classifier = read_workflow(ESCALATING_WORKFLOW_DOCUMENT).steps

    assert classifier.confidence == "confidence"

    (condition,) = escalate.conditions

    assert condition.source == WorkflowValueReference(
        producer_step_id=CLASSIFY_STEP_ID,
        name="confidence",
    )
    assert condition.operator is WorkflowConditionOperator.LESS_THAN
    assert condition.expected == 0.8


def test_only_the_classifier_is_held_to_cheap_models() -> None:
    escalate, classifier = read_workflow(ESCALATING_WORKFLOW_DOCUMENT).steps

    assert isinstance(classifier.specification, ContextPromptStrategySpec)
    assert isinstance(escalate.specification, ContextPromptStrategySpec)

    cheap = classifier.specification.model_selection
    strong = escalate.specification.model_selection

    assert cheap.model_dump()["requirements"]["maximum_input_usd_per_million_tokens"] == 0.5
    assert cheap.model_dump()["requirements"]["maximum_output_usd_per_million_tokens"] == 1.5
    assert strong.model_dump()["requirements"]["maximum_input_usd_per_million_tokens"] is None


# Running it


def test_a_ticket_the_classifier_is_sure_of_does_not_escalate() -> None:
    models = Models()

    run, category = classify(models, "Charged twice")

    assert category == "billing"
    assert step(run, CLASSIFY_STEP_ID).confidence == 0.97
    assert model_of(step(run, CLASSIFY_STEP_ID)) == "compact"
    assert step(run, ESCALATE_STEP_ID).status is WorkflowStepStatus.SKIPPED
    assert models.frontier.prompts == []


def test_an_unsure_ticket_escalates_to_the_stronger_model() -> None:
    models = Models()

    run, category = classify(models, UNSURE_SUBJECT)

    assert category == "billing"
    assert step(run, CLASSIFY_STEP_ID).confidence == 0.55
    assert step(run, ESCALATE_STEP_ID).status is WorkflowStepStatus.EXECUTED
    assert model_of(step(run, ESCALATE_STEP_ID)) == "frontier"

    (escalation_prompt,) = models.frontier.prompts

    assert "The first classifier's guess at its category: account" in escalation_prompt


def test_escalation_lets_the_cheap_classifier_pass_the_classifier_benchmark() -> None:
    models = Models()
    candidate = escalating_candidate(models)

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(read_benchmark(CLASSIFY_BENCHMARK_DOCUMENT), every_case)
    )

    assert (result.cases_run, result.cases_passed, result.run_failures) == (6, 6, 0)
    assert len(models.frontier.prompts) == 1


def test_the_cheap_model_alone_misses_the_ticket_it_was_unsure_of() -> None:
    models = Models()

    candidate = generate_workflow_candidate(
        specification=read_workflow(CLASSIFY_WORKFLOW_DOCUMENT),
        catalog=scripted_catalog(("compact", 0.25)),
        registry=LanguageModelRegistry(models={"scripted/compact": models.compact}),
    )

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(read_benchmark(CLASSIFY_BENCHMARK_DOCUMENT), every_case)
    )

    assert (result.cases_run, result.cases_passed) == (6, 5)


def test_a_confidently_wrong_classifier_is_not_caught() -> None:
    models = Models(
        cheap_answers={**CHEAP_ANSWERS, UNSURE_SUBJECT: ("account", 0.9)},
    )

    run, category = classify(models, UNSURE_SUBJECT)

    assert category == "account"
    assert step(run, ESCALATE_STEP_ID).status is WorkflowStepStatus.SKIPPED


@pytest.mark.parametrize("confidence", ["high", 1.5, None])
def test_a_classifier_that_cannot_say_how_sure_it_is_fails(
    confidence: JsonValue,
) -> None:
    models = Models(
        cheap_answers={**CHEAP_ANSWERS, UNSURE_SUBJECT: ("account", confidence)},
    )

    candidate = escalating_candidate(models)

    with pytest.raises(Exception, match="confidence 'confidence' must be a number from 0 to 1"):
        run_with_input(
            candidate,
            {"subject": UNSURE_SUBJECT, "body": "Details.", "customer_tier": "standard"},
        )

    assert len(models.compact.prompts) == 2
    assert models.frontier.prompts == []
