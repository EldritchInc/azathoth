"""Tests for semantic judging in benchmark and optimization commands."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

import azathoth.cli.benchmarks as benchmark_commands
import azathoth.cli.workflows as workflow_commands
from azathoth.cli import (
    CliRuntimeConfiguration,
    compare_benchmarks,
    optimize_configured_workflow,
    optimize_workflow,
    run_benchmark,
)
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    JudgeEntry,
    JudgeRotation,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
    SQLiteJudgeRotationRepository,
)
from azathoth.providers import (
    LanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelPortfolio,
    ModelPortfolioEntry,
    ModelPricing,
)
from azathoth.runtime import (
    AzathothRuntime,
    JudgeUnavailableError,
)
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunEvaluationRepository,
    WorkflowCatalog,
    WorkflowScoringPolicy,
)
from tests.cli.test_optimization import (
    CHEAP_IDENTIFIER,
    EXPENSIVE_IDENTIFIER,
    WORKFLOW_ID,
    CostedDeterministicLanguageModel,
    create_models,
    create_portfolio,
    create_workflow,
)
from tests.evaluation.test_semantic import (
    PASS_REPLY,
    ScriptedJudgeModel,
)

BENCHMARK_ID = UUID("5e5e5e5e-5e5e-4e5e-8e5e-5e5e5e5e5e5e")

EXACT_CASE_ID = UUID("5e5e5e5e-5e5e-4e5e-8e5e-000000000001")

SEMANTIC_CASE_ID = UUID("5e5e5e5e-5e5e-4e5e-8e5e-000000000002")

SECOND_WORKFLOW_ID = UUID("5e5e5e5e-5e5e-4e5e-8e5e-0000000000ff")

JUDGE = JudgeEntry(
    provider="judges",
    model="gamma",
)

JUDGE_COST_USD = 0.25


def create_dataset(
    *,
    semantic: bool = True,
) -> BenchmarkDataset:
    """Create a benchmark with one exact case and, optionally, one semantic case."""

    exact = BenchmarkCase(
        id=EXACT_CASE_ID,
        input="first",
        expected=ExpectedOutcome(
            description="The workflow returns success.",
            value="success",
            comparison=OutcomeComparison.EXACT,
        ),
    )

    semantic_case = BenchmarkCase(
        id=SEMANTIC_CASE_ID,
        input="second",
        expected=ExpectedOutcome(
            description="The workflow reports that it worked.",
            value="It worked.",
            comparison=OutcomeComparison.SEMANTIC,
        ),
    )

    return BenchmarkDataset(
        id=BENCHMARK_ID,
        name="semantic-commands",
        description="Benchmark mixing exact and semantic judging.",
        cases=((exact, semantic_case) if semantic else (exact,)),
    )


def create_runtime(
    judge: ScriptedJudgeModel,
    *,
    judge_authorized: bool = True,
    judges: JudgeRotation | None = None,
    second_workflow: bool = False,
) -> AzathothRuntime:
    """Create a runtime whose judge is authorized but never a cheaper candidate.

    The judge model is priced far above both candidate models and authorized
    last, so portfolio selection and cheaper-model substitution never pick it.
    """

    workflow = create_workflow()

    specifications = (
        (
            workflow,
            workflow.model_copy(
                update={
                    "metadata": workflow.metadata.model_copy(
                        update={
                            "id": SECOND_WORKFLOW_ID,
                        },
                    ),
                },
            ),
        )
        if second_workflow
        else (workflow,)
    )

    language_models: dict[str, LanguageModel] = {
        EXPENSIVE_IDENTIFIER: CostedDeterministicLanguageModel(
            model="expensive",
            estimated_cost_usd=0.10,
        ),
        CHEAP_IDENTIFIER: CostedDeterministicLanguageModel(
            model="cheap",
            estimated_cost_usd=0.01,
        ),
        JUDGE.identifier: judge,
    }

    return AzathothRuntime(
        workflows=WorkflowCatalog(
            specifications=specifications,
        ),
        models=ModelCatalog(
            models=(
                *create_models().models,
                ModelMetadata(
                    provider="judges",
                    model="gamma",
                    display_name="Gamma Judge",
                    context_window_tokens=4096,
                    pricing=ModelPricing(
                        input_usd_per_million_tokens=100.0,
                        output_usd_per_million_tokens=200.0,
                    ),
                ),
            ),
        ),
        portfolio=ModelPortfolio(
            entries=(
                *create_portfolio().entries,
                *(
                    (
                        ModelPortfolioEntry(
                            provider="judges",
                            model="gamma",
                        ),
                    )
                    if judge_authorized
                    else ()
                ),
            ),
        ),
        language_models=LanguageModelRegistry(language_models),
        judges=(
            judges
            if judges is not None
            else JudgeRotation(
                entries=(JUDGE,),
            )
        ),
    )


def configure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime: AzathothRuntime,
    dataset: BenchmarkDataset,
) -> Path:
    """Persist the workflow, benchmark, and judge rotation the runtime describes."""

    database = tmp_path / "azathoth.db"

    for specification in runtime.workflows.specifications:
        SQLiteWorkflowRepository(database).save(specification)

    SQLiteBenchmarkRepository(database).save(dataset)

    for entry in runtime.judges.entries:
        SQLiteJudgeRotationRepository(database).add(entry)

    configuration = CliRuntimeConfiguration(
        database=database,
    )

    monkeypatch.setattr(
        CliRuntimeConfiguration,
        "from_environment",
        lambda: configuration,
    )

    monkeypatch.setattr(
        benchmark_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    monkeypatch.setattr(
        workflow_commands,
        "load_runtime",
        lambda _configuration: runtime,
    )

    return database


def test_benchmark_run_judges_semantic_case_and_reports_judge_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    judge = ScriptedJudgeModel(
        PASS_REPLY,
        cost_usd=JUDGE_COST_USD,
    )

    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(judge),
        dataset=create_dataset(),
    )

    result = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert len(judge.prompts) == 1
    assert (
        "Cases Passed: 2\n"
        "Accuracy: 1.000000\n"
        "Passed (exact): 1/1\n"
        "Passed (semantic): 1/1\n"
        "Run failures: 0\n"
    ) in captured.out
    assert captured.out.endswith("Total Cost: $0.200000\nJudge Calls: 1\nJudge Cost: $0.250000\n")


def test_benchmark_run_without_semantic_cases_ignores_unusable_judges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    judge = ScriptedJudgeModel()

    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            judge,
            judge_authorized=False,
        ),
        dataset=create_dataset(
            semantic=False,
        ),
    )

    result = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert judge.prompts == []
    assert "Judge Calls" not in captured.out
    assert "Judge Cost" not in captured.out


def test_benchmark_run_rejects_unauthorized_judge_before_any_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    judge = ScriptedJudgeModel()

    database = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            judge,
            judge_authorized=False,
        ),
        dataset=create_dataset(),
    )

    result = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Judge model judges/gamma is not authorized.\n"
    assert judge.prompts == []
    assert SQLiteWorkflowRunEvaluationRepository(database).evaluations() == ()


def test_benchmark_run_reports_judging_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            ScriptedJudgeModel(RuntimeError("down")),
        ),
        dataset=create_dataset(),
    )

    result = run_benchmark(
        benchmark_id=BENCHMARK_ID,
        workflow_id=WORKFLOW_ID,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        "Semantic judging failed with every judge: judges/gamma raised RuntimeError: down.\n"
    )


def test_benchmark_compare_judges_semantic_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    judge = ScriptedJudgeModel(
        PASS_REPLY,
        PASS_REPLY,
    )

    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            judge,
            second_workflow=True,
        ),
        dataset=create_dataset(),
    )

    result = compare_benchmarks(
        benchmark_id=BENCHMARK_ID,
        workflow_ids=(
            WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
    )

    captured = capsys.readouterr()

    assert result == 0
    assert captured.err == ""
    assert len(judge.prompts) == 2
    assert captured.out.count("Quality: 1.000000") == 2


def test_benchmark_compare_rejects_unavailable_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            ScriptedJudgeModel(),
            judge_authorized=False,
            second_workflow=True,
        ),
        dataset=create_dataset(),
    )

    result = compare_benchmarks(
        benchmark_id=BENCHMARK_ID,
        workflow_ids=(
            WORKFLOW_ID,
            SECOND_WORKFLOW_ID,
        ),
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.err == "Judge model judges/gamma is not authorized.\n"


def test_optimize_records_semantic_evaluations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            ScriptedJudgeModel(
                PASS_REPLY,
                PASS_REPLY,
                PASS_REPLY,
            ),
        ),
        dataset=create_dataset(),
    )

    result = optimize_workflow(
        workflow_id=WORKFLOW_ID,
        benchmark_id=BENCHMARK_ID,
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
        generations=2,
    )

    capsys.readouterr()

    evaluator_names = tuple(
        record.evaluation.evaluator_name
        for record in SQLiteWorkflowRunEvaluationRepository(database).evaluations()
    )

    assert result == 0
    assert evaluator_names.count("semantic-judge") == 3
    assert evaluator_names.count("exact-match") == 3


def test_optimize_rejects_unavailable_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runtime=create_runtime(
            ScriptedJudgeModel(),
            judge_authorized=False,
        ),
        dataset=create_dataset(),
    )

    result = optimize_workflow(
        workflow_id=WORKFLOW_ID,
        benchmark_id=BENCHMARK_ID,
        target_latency_seconds=60.0,
        target_cost_usd=1.0,
        generations=1,
    )

    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err == "Judge model judges/gamma is not authorized.\n"


def test_judge_cost_never_changes_optimization_scorecards() -> None:
    def optimize(
        judge_cost_usd: float,
    ) -> list[tuple[float, float, float, float, float]]:
        runtime = create_runtime(
            ScriptedJudgeModel(
                PASS_REPLY,
                PASS_REPLY,
                PASS_REPLY,
                cost_usd=judge_cost_usd,
            ),
        )

        session = asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
                dataset=create_dataset(),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.01,
                ),
                max_generations=2,
            )
        )

        return [
            (
                scorecard.quality_score,
                scorecard.reliability_score,
                scorecard.latency_score,
                scorecard.cost_score,
                scorecard.overall_score,
            )
            for generation in session.generations
            for scorecard in generation.previous_experiment.scorecards
        ]

    assert optimize(0.0) == optimize(1000.0)


def test_optimization_service_rejects_semantic_benchmark_without_usable_judges() -> None:
    runtime = create_runtime(
        ScriptedJudgeModel(),
        judges=JudgeRotation(),
    )

    with pytest.raises(
        JudgeUnavailableError,
        match="^No semantic judges are configured.$",
    ):
        asyncio.run(
            optimize_configured_workflow(
                runtime=runtime,
                workflow_id=WORKFLOW_ID,
                dataset=create_dataset(),
                scoring_policy=WorkflowScoringPolicy(
                    target_latency_seconds=60.0,
                    target_cost_usd=0.01,
                ),
                max_generations=1,
            )
        )
