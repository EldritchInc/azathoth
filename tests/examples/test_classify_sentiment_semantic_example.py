"""Tests proving the checked-in semantic sentiment benchmark works with judges."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    OutcomeEvaluator,
    SemanticEvaluator,
    decode_benchmark_document,
    default_comparison_evaluators,
    encode_benchmark_document,
)
from azathoth.providers import (
    ModelResponse,
    Prompt,
)
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
)
from tests.examples.test_classify_sentiment_examples import (
    KeywordSentimentModel,
    create_candidate,
)

PROJECT_ROOT = Path(__file__).parents[2]

SEMANTIC_BENCHMARK_DOCUMENT = (
    PROJECT_ROOT / "examples" / "benchmarks" / "classify-sentiment-semantic.json"
)

BENCHMARK_ID = UUID("5e2e0b6a-3c1d-4b7e-9f22-000000000000")

JUDGE = JudgeEntry(
    provider="judges",
    model="label",
)


class LabelJudgeModel:
    """Pass when the prompted actual answer equals the prompted expected answer."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: Prompt,
    ) -> ModelResponse:
        """Return a verdict comparing the two JSON answers in the prompt."""

        self.prompts.append(prompt.text)

        expected = _answer_after(prompt.text, "Expected answer (JSON):")
        actual = _answer_after(prompt.text, "Actual answer (JSON):")

        verdict = "pass" if expected == actual else "fail"

        return ModelResponse(
            text=json.dumps(
                {
                    "verdict": verdict,
                    "reason": f"Expected {expected!r}, got {actual!r}.",
                }
            ),
            provider="judges",
            model="label",
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            latency_ms=0,
            estimated_cost_usd=0.0,
        )


def _answer_after(
    text: str,
    heading: str,
) -> object:
    """Return the JSON value on the line after one prompt heading."""

    lines = text.split("\n")

    return json.loads(lines[lines.index(heading) + 1])


def read_benchmark() -> BenchmarkDataset:
    """Decode the checked-in semantic sentiment benchmark."""

    return decode_benchmark_document(
        SEMANTIC_BENCHMARK_DOCUMENT.read_text(
            encoding="utf-8",
        )
    )


def test_semantic_benchmark_example_is_canonical() -> None:
    document = SEMANTIC_BENCHMARK_DOCUMENT.read_text(
        encoding="utf-8",
    )

    assert document.rstrip("\n") == encode_benchmark_document(read_benchmark())


def test_semantic_benchmark_example_judges_every_case_semantically() -> None:
    benchmark = read_benchmark()

    assert benchmark.id == BENCHMARK_ID
    assert benchmark.comparison_counts() == {
        OutcomeComparison.SEMANTIC: 3,
    }
    assert all(isinstance(case.input, str) for case in benchmark.cases)


def test_semantic_benchmark_example_runs_with_one_judge() -> None:
    judge = LabelJudgeModel()

    candidate = create_candidate(KeywordSentimentModel())

    def every_case(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return candidate

    result = asyncio.run(
        WorkflowBenchmarkRunner(
            evaluator=OutcomeEvaluator(
                default_comparison_evaluators(
                    semantic=SemanticEvaluator(
                        rotation=JudgeRotation(
                            entries=(JUDGE,),
                        ),
                        models={
                            JUDGE.identifier: judge,
                        },
                    ),
                )
            ),
        ).run(
            read_benchmark(),
            every_case,
        )
    )

    assert result.cases_passed == 3
    assert result.judge_calls == 3
    assert len(judge.prompts) == 3
    assert result.total_cost_usd == 0.0
