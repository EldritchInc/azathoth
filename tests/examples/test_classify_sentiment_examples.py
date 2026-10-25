"""Tests proving the checked-in sentiment workflow and benchmark work together."""

import asyncio
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    OutcomeComparison,
    OutcomeEvaluator,
    decode_benchmark_document,
    encode_benchmark_document,
)
from azathoth.prompting import ContextPromptStrategySpec
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelResponse,
    Prompt,
)
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowSpecification,
    WorkflowValueReference,
    create_production_invocation,
    create_workflow_input_event,
    decode_workflow_document,
    encode_workflow_document,
)
from tests.model_authorization import generate_workflow_candidate

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_DOCUMENT = PROJECT_ROOT / "examples" / "workflows" / "classify-sentiment.json"

BENCHMARK_DOCUMENT = PROJECT_ROOT / "examples" / "benchmarks" / "classify-sentiment.json"

WORKFLOW_ID = UUID("5e2e0b6a-3c1d-4b7e-9f20-000000000001")

STEP_ID = UUID("5e2e0b6a-3c1d-4b7e-9f20-000000000002")

BENCHMARK_ID = UUID("5e2e0b6a-3c1d-4b7e-9f21-000000000000")

MODEL_IDENTIFIER = "deterministic/sentiment"

NEGATIVE_WORDS = (
    "waste",
    "rude",
    "cold",
)


class KeywordSentimentModel:
    """Classify the text after `Text:` by keyword and record every prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return the keyword classification of the prompted text."""

        self.prompts.append(prompt.text)

        text = prompt.text.rsplit("Text: ", 1)[-1].lower()

        label = "negative" if any(word in text for word in NEGATIVE_WORDS) else "positive"

        return ModelResponse(
            text=label,
            provider="deterministic",
            model="sentiment",
            prompt_tokens=len(prompt.text.split()),
            completion_tokens=1,
            total_tokens=len(prompt.text.split()) + 1,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def read_workflow() -> WorkflowSpecification:
    """Decode the checked-in sentiment workflow."""

    return decode_workflow_document(
        WORKFLOW_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def read_benchmark() -> BenchmarkDataset:
    """Decode the checked-in sentiment benchmark."""

    return decode_benchmark_document(
        BENCHMARK_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def read_specification() -> ContextPromptStrategySpec:
    """Return the workflow's one context prompt specification."""

    specification = read_workflow().steps[0].specification

    assert isinstance(
        specification,
        ContextPromptStrategySpec,
    )

    return specification


def create_candidate(
    model: KeywordSentimentModel,
) -> WorkflowCandidate:
    """Generate an executable candidate backed by the keyword model."""

    return generate_workflow_candidate(
        specification=read_workflow(),
        catalog=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="deterministic",
                    model="sentiment",
                    display_name="Deterministic Sentiment",
                    context_window_tokens=8_192,
                ),
            ),
        ),
        registry=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: model,
            },
        ),
    )


def test_sentiment_workflow_example_is_canonical() -> None:
    document = WORKFLOW_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert document.rstrip("\n") == encode_workflow_document(read_workflow())


def test_sentiment_workflow_example_declares_its_result() -> None:
    workflow = read_workflow()

    assert workflow.metadata.id == WORKFLOW_ID
    assert isinstance(workflow.result, WorkflowValueReference)
    assert workflow.result.producer_step_id == STEP_ID
    assert workflow.result.name == "sentiment"


def test_sentiment_workflow_example_binds_the_workflow_input() -> None:
    bindings = read_specification().template.bindings

    assert len(bindings) == 1
    assert bindings[0].variable_name == "text"
    assert bindings[0].event_type == WORKFLOW_INPUT_EVENT_TYPE
    assert bindings[0].field_name == "input"


def test_sentiment_benchmark_example_is_canonical() -> None:
    document = BENCHMARK_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert document.rstrip("\n") == encode_benchmark_document(read_benchmark())


def test_sentiment_benchmark_example_mixes_supported_comparisons() -> None:
    benchmark = read_benchmark()

    assert benchmark.id == BENCHMARK_ID
    assert benchmark.comparison_counts() == {
        OutcomeComparison.EXACT: 2,
        OutcomeComparison.NORMALIZED: 2,
        OutcomeComparison.SCHEMA: 1,
    }

    evaluator = OutcomeEvaluator()

    assert all(evaluator.supports(case.expected.comparison) for case in benchmark.cases)


def test_every_benchmark_case_input_renders_into_the_prompt() -> None:
    template = read_specification().template

    for case in read_benchmark().cases:
        prompt = template.render(
            Context(
                events=(
                    create_workflow_input_event(
                        case.input,
                        producer="azathoth.benchmark",
                    ),
                )
            )
        )

        assert prompt.text.endswith(f"Text: {case.input}")


def test_production_invocation_renders_the_same_prompt_as_a_benchmark_case() -> None:
    template = read_specification().template

    case = read_benchmark().cases[0]

    invoked = template.render(
        create_production_invocation(
            workflow_id=WORKFLOW_ID,
            payload=case.input,
        ).initial_context
    )

    benchmarked = template.render(
        Context(
            events=(
                create_workflow_input_event(
                    case.input,
                    producer="azathoth.benchmark",
                ),
            )
        )
    )

    assert invoked == benchmarked


def test_sentiment_benchmark_runs_the_example_workflow_end_to_end() -> None:
    model = KeywordSentimentModel()

    candidate = create_candidate(model)

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    benchmark = read_benchmark()

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            benchmark,
            every_case,
        )
    )

    assert model.prompts == [
        read_specification().template.text.format(text=case.input) for case in benchmark.cases
    ]
    assert result.cases_run == 5
    assert result.cases_passed == 5
    assert result.run_failures == 0
