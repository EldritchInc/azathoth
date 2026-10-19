"""Tests for per-case comparisons during workflow benchmark execution."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedOutcome,
    OutcomeComparison,
    UnsupportedComparisonError,
)
from azathoth.prompting import (
    PortfolioModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import (
    DeterministicLanguageModel,
    LanguageModelRegistry,
    ModelCatalog,
    ModelMetadata,
    ModelRequirements,
    Prompt,
)
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowMetadata,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

DATASET_ID = UUID("11111111-1111-1111-1111-111111111111")
EXACT_CASE_ID = UUID("22222222-2222-2222-2222-222222222221")
NORMALIZED_CASE_ID = UUID("22222222-2222-2222-2222-222222222222")
SCHEMA_CASE_ID = UUID("22222222-2222-2222-2222-222222222223")
SEMANTIC_CASE_ID = UUID("22222222-2222-2222-2222-222222222224")
WORKFLOW_ID = UUID("44444444-4444-4444-4444-444444444444")
STEP_ID = UUID("55555555-5555-5555-5555-555555555555")
STRATEGY_ID = UUID("66666666-6666-6666-6666-666666666666")

MODEL_IDENTIFIER = "deterministic/classifier-small"

RESPONSES = {
    EXACT_CASE_ID: "Refund",
    NORMALIZED_CASE_ID: "  Billing\n",
    SCHEMA_CASE_ID: "account",
    SEMANTIC_CASE_ID: "a refund, please",
}


def create_case(
    case_id: UUID,
    comparison: OutcomeComparison,
    expected: JsonValue,
) -> BenchmarkCase:
    """Create one benchmark case judged by one comparison."""

    return BenchmarkCase(
        id=case_id,
        input=f"Ticket {case_id}",
        expected=ExpectedOutcome(
            description=f"Expected {comparison.value} outcome",
            value=expected,
            comparison=comparison,
        ),
    )


def create_mixed_dataset() -> BenchmarkDataset:
    """Create a benchmark whose cases use different comparisons."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="mixed-comparisons",
        description="Cases judged by their own comparisons.",
        cases=(
            create_case(EXACT_CASE_ID, OutcomeComparison.EXACT, "refund"),
            create_case(NORMALIZED_CASE_ID, OutcomeComparison.NORMALIZED, "billing"),
            create_case(
                SCHEMA_CASE_ID,
                OutcomeComparison.SCHEMA,
                {"type": "string", "enum": ["refund", "billing", "account"]},
            ),
        ),
    )


def create_candidate(
    case: BenchmarkCase,
) -> WorkflowCandidate:
    """Create one candidate that returns the scripted response for a case."""

    specification = WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Ticket classification",
            description="Classify benchmark tickets.",
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="Classify ticket",
                        description="Return a ticket label.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text=f"Classify this ticket.\n\nTicket: {case.input}",
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
        result=WorkflowValueReference(
            producer_step_id=STEP_ID,
            name="classification",
        ),
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=ModelCatalog(
            models=(
                ModelMetadata(
                    provider="deterministic",
                    model="classifier-small",
                    display_name="Deterministic Classifier",
                    context_window_tokens=8_192,
                ),
            ),
        ),
        registry=LanguageModelRegistry(
            models={
                MODEL_IDENTIFIER: DeterministicLanguageModel(
                    provider="deterministic",
                    model="classifier-small",
                    response_text=RESPONSES[case.id],
                ),
            },
        ),
    )


def test_benchmark_judges_each_case_by_its_own_comparison() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_mixed_dataset(),
            create_candidate,
        )
    )

    judged = {
        case.case_id: (case.evaluation.evaluator_name, case.evaluation.passed)
        for case in result.cases
    }

    assert judged == {
        EXACT_CASE_ID: ("exact-match", False),
        NORMALIZED_CASE_ID: ("normalized-match", True),
        SCHEMA_CASE_ID: ("json-schema", True),
    }
    assert result.cases_passed == 2


def test_benchmark_records_each_case_comparison() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            create_mixed_dataset(),
            create_candidate,
        )
    )

    assert [(case.case_id, case.comparison) for case in result.cases] == [
        (EXACT_CASE_ID, OutcomeComparison.EXACT),
        (NORMALIZED_CASE_ID, OutcomeComparison.NORMALIZED),
        (SCHEMA_CASE_ID, OutcomeComparison.SCHEMA),
    ]


def test_benchmark_tallies_passes_per_comparison() -> None:
    dataset = create_mixed_dataset().model_copy(
        update={
            "cases": (
                *create_mixed_dataset().cases,
                create_case(
                    SEMANTIC_CASE_ID,
                    OutcomeComparison.EXACT,
                    "a refund, please",
                ),
            ),
        }
    )

    result = asyncio.run(
        WorkflowBenchmarkRunner().run(
            dataset,
            create_candidate,
        )
    )

    assert [
        (tally.comparison, tally.cases_passed, tally.cases_run)
        for tally in result.comparison_tallies
    ] == [
        (OutcomeComparison.EXACT, 1, 2),
        (OutcomeComparison.NORMALIZED, 1, 1),
        (OutcomeComparison.SCHEMA, 1, 1),
    ]


def test_benchmark_rejects_unsupported_comparison_before_executing_any_case() -> None:
    dataset = create_mixed_dataset().model_copy(
        update={
            "cases": (
                *create_mixed_dataset().cases,
                create_case(
                    SEMANTIC_CASE_ID,
                    OutcomeComparison.SEMANTIC,
                    "The customer asks for a refund.",
                ),
            ),
        }
    )

    created: list[UUID] = []

    def recording_candidate(
        case: BenchmarkCase,
    ) -> WorkflowCandidate:
        created.append(case.id)

        return create_candidate(case)

    with pytest.raises(
        UnsupportedComparisonError,
        match=(
            f"^Benchmark case {SEMANTIC_CASE_ID} uses comparison 'semantic', "
            "which is not supported yet.$"
        ),
    ):
        asyncio.run(
            WorkflowBenchmarkRunner().run(
                dataset,
                recording_candidate,
            )
        )

    assert created == []
