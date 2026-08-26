"""End-to-end workflow execution from durable benchmark datasets."""

import asyncio
from pathlib import Path
from uuid import UUID

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCatalogLoader,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelCatalogLoader,
    ModelMetadata,
    ModelRequirements,
    Prompt,
    SQLiteModelRepository,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    SQLiteWorkflowRepository,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowCatalogLoader,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_workflow_candidate,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")

POSITIVE_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")

NEGATIVE_CASE_ID = UUID("33333333-3333-3333-3333-333333333333")

WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")

STEP_ID = UUID("55555555-5555-5555-5555-555555555555")

STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_PROVIDER = "deterministic"
MODEL_NAME = "benchmark-model"
MODEL_IDENTIFIER = f"{MODEL_PROVIDER}/{MODEL_NAME}"


def create_dataset() -> BenchmarkDataset:
    """Create a deterministic reusable classification benchmark."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="classification benchmark",
        description=("Verify positive and negative classification behavior."),
        version="1.2.3",
        cases=(
            BenchmarkCase(
                id=POSITIVE_CASE_ID,
                input="good",
                expected=ExpectedOutcome(
                    description=("Classify the positive input as positive."),
                    value="positive",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "positive",
                    "difficulty": "easy",
                },
            ),
            BenchmarkCase(
                id=NEGATIVE_CASE_ID,
                input="bad",
                expected=ExpectedOutcome(
                    description=("Classify the negative input as negative."),
                    value="negative",
                    comparison=OutcomeComparison.EXACT,
                ),
                metadata={
                    "category": "negative",
                    "difficulty": "easy",
                },
            ),
        ),
    )


def create_workflow() -> WorkflowSpecification:
    """Create the durable workflow used by the benchmark."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="benchmark classification workflow",
            description=("Classify one benchmark case using a language model."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="benchmark classifier",
                        description=("Classify one deterministic benchmark input."),
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the supplied benchmark input.",
                    ),
                    model_selection=PortfolioModelSelection(
                        requirements=ModelRequirements(),
                    ),
                ),
                outputs=(
                    WorkflowValueBinding(
                        name="classification",
                    ),
                ),
            ),
        ),
    )


def create_model_metadata() -> ModelMetadata:
    """Create durable metadata for the benchmark execution model."""

    return ModelMetadata(
        provider=MODEL_PROVIDER,
        model=MODEL_NAME,
        display_name="Benchmark Model",
        context_window_tokens=8_192,
    )


def persist_configuration(
    *,
    benchmark_database: Path,
    workflow_database: Path,
    model_database: Path,
) -> None:
    """Persist the complete declarative benchmark configuration."""

    SQLiteBenchmarkRepository(benchmark_database).save(create_dataset())

    SQLiteWorkflowRepository(workflow_database).save(create_workflow())

    SQLiteModelRepository(model_database).save(create_model_metadata())


def reconstruct_dataset(
    database: Path,
) -> BenchmarkDataset:
    """Reconstruct the durable benchmark dataset."""

    catalog = BenchmarkCatalogLoader(SQLiteBenchmarkRepository(database)).load_catalog()

    dataset = catalog.get(DATASET_ID)

    assert dataset is not None

    return dataset


def reconstruct_workflow(
    database: Path,
) -> WorkflowSpecification:
    """Reconstruct the durable benchmark workflow."""

    catalog = WorkflowCatalogLoader(SQLiteWorkflowRepository(database)).load_catalog()

    workflow = catalog.get(WORKFLOW_ID)

    assert workflow is not None

    return workflow


def reconstruct_model_catalog(
    database: Path,
) -> ModelCatalog:
    """Reconstruct the durable benchmark model catalog."""

    return ModelCatalogLoader(SQLiteModelRepository(database)).load_catalog()


def response_for_case(
    case: BenchmarkCase,
) -> str:
    """Return deterministic model output from persisted benchmark input."""

    if case.input == "good":
        return "positive"

    if case.input == "bad":
        return "negative"

    raise AssertionError(f"Unexpected benchmark input {case.input!r}.")


def create_registry_for_case(
    case: BenchmarkCase,
) -> LanguageModelRegistry:
    """Create runtime execution capability for one benchmark case."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                response_text=response_for_case(case),
            ),
        }
    )


def test_durable_benchmark_reconstructs_exact_dataset(
    tmp_path: Path,
) -> None:
    benchmark_database = tmp_path / "benchmarks.db"
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"

    persist_configuration(
        benchmark_database=benchmark_database,
        workflow_database=workflow_database,
        model_database=model_database,
    )

    restored = reconstruct_dataset(benchmark_database)

    assert restored == create_dataset()
    assert restored is not create_dataset()

    assert restored.id == DATASET_ID
    assert restored.name == "classification benchmark"
    assert restored.version == "1.2.3"

    assert tuple(case.id for case in restored.cases) == (
        POSITIVE_CASE_ID,
        NEGATIVE_CASE_ID,
    )


def test_durable_benchmark_preserves_cases_and_expectations(
    tmp_path: Path,
) -> None:
    benchmark_database = tmp_path / "benchmarks.db"
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"

    persist_configuration(
        benchmark_database=benchmark_database,
        workflow_database=workflow_database,
        model_database=model_database,
    )

    restored = reconstruct_dataset(benchmark_database)

    positive = restored.cases[0]
    negative = restored.cases[1]

    assert positive.id == POSITIVE_CASE_ID
    assert positive.input == "good"
    assert positive.expected.value == "positive"
    assert positive.expected.comparison is OutcomeComparison.EXACT
    assert positive.metadata == {
        "category": "positive",
        "difficulty": "easy",
    }

    assert negative.id == NEGATIVE_CASE_ID
    assert negative.input == "bad"
    assert negative.expected.value == "negative"
    assert negative.expected.comparison is OutcomeComparison.EXACT
    assert negative.metadata == {
        "category": "negative",
        "difficulty": "easy",
    }


def test_durable_benchmark_executes_after_full_configuration_restart(
    tmp_path: Path,
) -> None:
    benchmark_database = tmp_path / "benchmarks.db"
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"

    persist_configuration(
        benchmark_database=benchmark_database,
        workflow_database=workflow_database,
        model_database=model_database,
    )

    dataset = reconstruct_dataset(benchmark_database)

    workflow = reconstruct_workflow(workflow_database)

    model_catalog = reconstruct_model_catalog(model_database)

    def candidate_factory(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return generate_workflow_candidate(
            specification=workflow,
            catalog=model_catalog,
            registry=create_registry_for_case(case),
        )

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            dataset,
            candidate_factory,
            output_name="classification",
        )
    )

    assert result.dataset_id == DATASET_ID
    assert result.cases_run == 2
    assert result.cases_passed == 2
    assert result.accuracy == 1.0

    assert tuple(case.case_id for case in result.cases) == (
        POSITIVE_CASE_ID,
        NEGATIVE_CASE_ID,
    )

    assert all(case.evaluation.passed for case in result.cases)


def test_durable_benchmark_inputs_drive_reconstructed_execution(
    tmp_path: Path,
) -> None:
    benchmark_database = tmp_path / "benchmarks.db"
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"

    persist_configuration(
        benchmark_database=benchmark_database,
        workflow_database=workflow_database,
        model_database=model_database,
    )

    dataset = reconstruct_dataset(benchmark_database)

    workflow = reconstruct_workflow(workflow_database)

    model_catalog = reconstruct_model_catalog(model_database)

    observed_inputs: list[object] = []

    def candidate_factory(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        observed_inputs.append(case.input)

        return generate_workflow_candidate(
            specification=workflow,
            catalog=model_catalog,
            registry=create_registry_for_case(case),
        )

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            dataset,
            candidate_factory,
            output_name="classification",
        )
    )

    assert observed_inputs == [
        "good",
        "bad",
    ]

    assert tuple(case.run.values_named("classification")[0].value for case in result.cases) == (
        "positive",
        "negative",
    )


def test_durable_benchmark_preserves_execution_identity_per_case(
    tmp_path: Path,
) -> None:
    benchmark_database = tmp_path / "benchmarks.db"
    workflow_database = tmp_path / "workflows.db"
    model_database = tmp_path / "models.db"

    persist_configuration(
        benchmark_database=benchmark_database,
        workflow_database=workflow_database,
        model_database=model_database,
    )

    dataset = reconstruct_dataset(benchmark_database)

    workflow = reconstruct_workflow(workflow_database)

    model_catalog = reconstruct_model_catalog(model_database)

    def candidate_factory(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        return generate_workflow_candidate(
            specification=workflow,
            catalog=model_catalog,
            registry=create_registry_for_case(case),
        )

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            dataset,
            candidate_factory,
            output_name="classification",
        )
    )

    assert len(result.cases) == 2

    for benchmark_case_result in result.cases:
        assert benchmark_case_result.run.workflow.id == WORKFLOW_ID

        assert benchmark_case_result.run.succeeded

        assert len(benchmark_case_result.run.steps) == 1

        execution = benchmark_case_result.run.steps[0].execution

        assert execution is not None
        assert execution.metrics is not None

        assert execution.metrics.provider == MODEL_PROVIDER

        assert execution.metrics.model == MODEL_NAME
