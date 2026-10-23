"""Tests for workflow results, emissions and rendering that name a value alone."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.cli.rendering import render_workflow_production
from azathoth.context import Context
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkDataset,
    EvaluationStatus,
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategySpec,
)
from azathoth.providers import Prompt
from azathoth.strategies import (
    Strategy,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    RUN_FAILURE_EVALUATOR_NAME,
    InMemoryWorkflowProductionRevisionRepository,
    InMemoryWorkflowProductionStateRepository,
    ProductionEmissionError,
    WorkflowBenchmarkRunner,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowNamedValueReference,
    WorkflowProductionEmission,
    WorkflowProductionState,
    WorkflowResultError,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    WorkflowValueReference,
    decode_workflow_document,
    describe_value_reference,
    emit_production_result,
    encode_workflow_document,
    promote_workflow_candidate,
    workflow_result,
    workflow_result_produced,
)
from tests.workflows.test_promotion import (
    PROMPT_STEP_ID,
    create_candidate,
    create_workflow,
)

WORKFLOW_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b01")

PRIMARY_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b11")
FALLBACK_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b12")
AUDIT_STEP_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b13")

PRIMARY_STRATEGY_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b21")
FALLBACK_STRATEGY_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b22")
AUDIT_STRATEGY_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b23")

DATASET_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b31")
CASE_ID = UUID("e5c3f8a4-6d7b-4a92-9ca3-4d5e6f7a8b32")

NO_FAILURES: frozenset[str] = frozenset()

NAMED_ANSWER = WorkflowNamedValueReference(
    name="answer",
)

NAMED_RESULT_ERROR = "Workflow result must name a value declared by at least one workflow step."

NAMED_CANDIDATE_RESULT_ERROR = (
    "Workflow candidate result must name a value declared by at least one candidate step."
)

EXECUTION_TIME = datetime(
    2026,
    10,
    23,
    13,
    30,
    tzinfo=UTC,
)

ANSWER_OUTPUT = (
    WorkflowValueBinding(
        name="answer",
    ),
)

AUDIT_OUTPUT = (
    WorkflowValueBinding(
        name="audit",
    ),
)


class NamedStrategy:
    """A strategy identified only by its name."""

    def __init__(
        self,
        *,
        strategy_id: UUID,
        name: str,
    ) -> None:
        self._metadata = StrategyMetadata(
            id=strategy_id,
            name=name,
            description=f"Execute {name}.",
            version="1.0.0",
        )

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return self._metadata

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return a placeholder outcome."""

        return StrategyOutcome(
            output=self.metadata.name,
        )


class AnswerExecutor(StrategyExecutor):
    """Answer with a value named after the strategy, or fail."""

    def __init__(
        self,
        *,
        failing: frozenset[str] = NO_FAILURES,
    ) -> None:
        self._failing = failing

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        """Answer, or fail a configured strategy."""

        name = strategy.metadata.name

        if name in self._failing:
            raise RuntimeError(f"{name} failed")

        return ExecutionResult(
            strategy_id=strategy.metadata.id,
            strategy_name=name,
            strategy_version=strategy.metadata.version,
            output=f"{name.lower()} answer",
            initial_context=context,
            final_context=context,
            started_at=EXECUTION_TIME,
            completed_at=EXECUTION_TIME,
        )


def create_metadata() -> WorkflowMetadata:
    """Return the shared workflow metadata."""

    return WorkflowMetadata(
        id=WORKFLOW_ID,
        name="Redundant answer",
        description="Answer two ways and return whichever answered.",
        version="1.0.0",
    )


def create_prompt_step(
    *,
    step_id: UUID,
    strategy_id: UUID,
    name: str,
    outputs: tuple[WorkflowValueBinding, ...],
) -> WorkflowStepSpecification:
    """Create one fixed-model prompt step specification."""

    return WorkflowStepSpecification(
        id=step_id,
        specification=PromptStrategySpec(
            metadata=StrategyMetadata(
                id=strategy_id,
                name=name,
                description=f"Execute {name}.",
                version="1.0.0",
            ),
            prompt=Prompt(
                text=f"Answer as {name}.",
            ),
            model_selection=FixedModelSelection(
                provider="test-provider",
                model="test-model",
            ),
        ),
        outputs=outputs,
    )


def create_specification(
    *,
    fallback_outputs: tuple[WorkflowValueBinding, ...] = ANSWER_OUTPUT,
) -> WorkflowSpecification:
    """Create a specification whose result names a redundantly produced answer."""

    return WorkflowSpecification(
        metadata=create_metadata(),
        steps=(
            create_prompt_step(
                step_id=AUDIT_STEP_ID,
                strategy_id=AUDIT_STRATEGY_ID,
                name="Audit",
                outputs=AUDIT_OUTPUT,
            ),
            create_prompt_step(
                step_id=PRIMARY_STEP_ID,
                strategy_id=PRIMARY_STRATEGY_ID,
                name="Primary",
                outputs=ANSWER_OUTPUT,
            ),
            create_prompt_step(
                step_id=FALLBACK_STEP_ID,
                strategy_id=FALLBACK_STRATEGY_ID,
                name="Fallback",
                outputs=fallback_outputs,
            ),
        ),
        result=NAMED_ANSWER,
    )


def create_candidate_steps() -> tuple[WorkflowCandidateStep, ...]:
    """Create executable steps whose two answer producers tolerate failure."""

    return (
        WorkflowCandidateStep(
            id=PRIMARY_STEP_ID,
            strategy=NamedStrategy(
                strategy_id=PRIMARY_STRATEGY_ID,
                name="Primary",
            ),
            outputs=ANSWER_OUTPUT,
            failure_policy=WorkflowFailurePolicy.CONTINUE,
        ),
        WorkflowCandidateStep(
            id=FALLBACK_STEP_ID,
            strategy=NamedStrategy(
                strategy_id=FALLBACK_STRATEGY_ID,
                name="Fallback",
            ),
            outputs=ANSWER_OUTPUT,
            failure_policy=WorkflowFailurePolicy.CONTINUE,
        ),
    )


def create_named_candidate() -> WorkflowCandidate:
    """Create an executable candidate declaring a name-only result."""

    return WorkflowCandidate(
        metadata=create_metadata(),
        steps=create_candidate_steps(),
        result=NAMED_ANSWER,
    )


def run_named_candidate(
    *,
    failing: frozenset[str] = NO_FAILURES,
) -> tuple[WorkflowCandidate, WorkflowRun]:
    """Run the name-only result candidate and return it with its run."""

    candidate = create_named_candidate()

    run = asyncio.run(
        WorkflowRunner(
            executor=AnswerExecutor(
                failing=failing,
            ),
        ).run(
            workflow=candidate,
            context=Context(),
        )
    )

    return (
        candidate,
        run,
    )


def test_workflow_accepts_name_only_result() -> None:
    assert create_specification().result == NAMED_ANSWER


def test_workflow_accepts_name_only_result_with_one_declaring_step() -> None:
    specification = create_specification(
        fallback_outputs=(),
    )

    assert specification.result == NAMED_ANSWER


def test_workflow_rejects_name_only_result_no_step_declares() -> None:
    with pytest.raises(
        ValidationError,
        match=NAMED_RESULT_ERROR,
    ):
        WorkflowSpecification(
            metadata=create_metadata(),
            steps=(
                create_prompt_step(
                    step_id=AUDIT_STEP_ID,
                    strategy_id=AUDIT_STRATEGY_ID,
                    name="Audit",
                    outputs=AUDIT_OUTPUT,
                ),
            ),
            result=NAMED_ANSWER,
        )


def test_workflow_document_records_name_only_result() -> None:
    document = json.loads(
        encode_workflow_document(create_specification()),
    )

    assert document["result"] == {
        "name": "answer",
    }


def test_workflow_document_round_trips_name_only_result() -> None:
    specification = create_specification()

    restored = decode_workflow_document(
        encode_workflow_document(specification),
    )

    assert restored == specification
    assert restored.result == NAMED_ANSWER


def test_candidate_accepts_name_only_result() -> None:
    assert create_named_candidate().result == NAMED_ANSWER


def test_candidate_rejects_name_only_result_no_step_declares() -> None:
    with pytest.raises(
        ValueError,
        match=NAMED_CANDIDATE_RESULT_ERROR,
    ):
        WorkflowCandidate(
            metadata=create_metadata(),
            steps=(
                WorkflowCandidateStep(
                    id=AUDIT_STEP_ID,
                    strategy=NamedStrategy(
                        strategy_id=AUDIT_STRATEGY_ID,
                        name="Audit",
                    ),
                    outputs=AUDIT_OUTPUT,
                ),
            ),
            result=NAMED_ANSWER,
        )


def test_name_only_result_uses_the_first_producer_in_step_order() -> None:
    candidate, run = run_named_candidate()

    assert (
        workflow_result(
            run,
            NAMED_ANSWER,
            steps=candidate.steps,
        )
        == "primary answer"
    )


def test_name_only_result_passes_over_a_failed_producer() -> None:
    candidate, run = run_named_candidate(
        failing=frozenset({"Primary"}),
    )

    assert (
        workflow_result(
            run,
            NAMED_ANSWER,
            steps=candidate.steps,
        )
        == "fallback answer"
    )


def test_name_only_result_rejects_run_without_any_producer() -> None:
    candidate, run = run_named_candidate(
        failing=frozenset(
            {
                "Primary",
                "Fallback",
            }
        ),
    )

    with pytest.raises(
        WorkflowResultError,
        match="^Workflow result 'answer' was not produced by any workflow step.$",
    ):
        workflow_result(
            run,
            NAMED_ANSWER,
            steps=candidate.steps,
        )


def test_name_only_result_is_reported_produced_by_any_producer() -> None:
    candidate, run = run_named_candidate(
        failing=frozenset({"Primary"}),
    )

    assert workflow_result_produced(
        run,
        NAMED_ANSWER,
        steps=candidate.steps,
    )


def test_name_only_result_is_reported_unproduced_without_producers() -> None:
    candidate, run = run_named_candidate(
        failing=frozenset(
            {
                "Primary",
                "Fallback",
            }
        ),
    )

    assert not workflow_result_produced(
        run,
        NAMED_ANSWER,
        steps=candidate.steps,
    )


def test_explicit_result_is_reported_produced_only_by_its_producer() -> None:
    candidate, run = run_named_candidate(
        failing=frozenset({"Primary"}),
    )

    assert not workflow_result_produced(
        run,
        WorkflowValueReference(
            producer_step_id=PRIMARY_STEP_ID,
            name="answer",
        ),
        steps=candidate.steps,
    )


def create_dataset() -> BenchmarkDataset:
    """Create a one-case benchmark expecting the fallback answer."""

    return BenchmarkDataset(
        id=DATASET_ID,
        name="redundant-answer",
        description="Benchmark a workflow with a redundant answer producer.",
        cases=(
            BenchmarkCase(
                id=CASE_ID,
                input="question",
                expected=ExpectedOutcome(
                    description="The fallback answer.",
                    value="fallback answer",
                    comparison=OutcomeComparison.EXACT,
                ),
            ),
        ),
    )


def run_benchmark(
    *,
    failing: frozenset[str],
) -> EvaluationStatus:
    """Benchmark the name-only result candidate and return its case status."""

    result = asyncio.run(
        WorkflowBenchmarkRunner(
            runner=WorkflowRunner(
                executor=AnswerExecutor(
                    failing=failing,
                ),
            ),
        ).run(
            create_dataset(),
            lambda case: create_named_candidate(),
        )
    )

    return result.cases[0].evaluation.status


def test_benchmark_judges_name_only_result_from_the_surviving_producer() -> None:
    assert (
        run_benchmark(
            failing=frozenset({"Primary"}),
        )
        is EvaluationStatus.PASSED
    )


def test_benchmark_records_run_failure_when_no_producer_survives() -> None:
    result = asyncio.run(
        WorkflowBenchmarkRunner(
            runner=WorkflowRunner(
                executor=AnswerExecutor(
                    failing=frozenset(
                        {
                            "Primary",
                            "Fallback",
                        }
                    ),
                ),
            ),
        ).run(
            create_dataset(),
            lambda case: create_named_candidate(),
        )
    )

    assert result.cases[0].evaluation.evaluator_name == RUN_FAILURE_EVALUATOR_NAME


def create_state() -> WorkflowProductionState:
    """Create production state emitting a name-only result."""

    return WorkflowProductionState(
        specification=create_specification(),
        emissions=(
            WorkflowProductionEmission(
                name="result",
                source=NAMED_ANSWER,
            ),
        ),
    )


def test_production_state_accepts_name_only_emission() -> None:
    assert create_state().emissions[0].source == NAMED_ANSWER


def test_production_state_rejects_undeclared_name_only_emission() -> None:
    with pytest.raises(
        ValidationError,
        match="Production emissions must reference declared workflow outputs.",
    ):
        WorkflowProductionState(
            specification=create_specification(),
            emissions=(
                WorkflowProductionEmission(
                    name="result",
                    source=WorkflowNamedValueReference(
                        name="summary",
                    ),
                ),
            ),
        )


def test_production_emits_name_only_result_from_first_producer() -> None:
    _, run = run_named_candidate()

    assert emit_production_result(
        state=create_state(),
        run=run,
    ) == {
        "result": "primary answer",
    }


def test_production_emits_name_only_result_from_surviving_producer() -> None:
    _, run = run_named_candidate(
        failing=frozenset({"Primary"}),
    )

    assert emit_production_result(
        state=create_state(),
        run=run,
    ) == {
        "result": "fallback answer",
    }


def test_production_rejects_name_only_result_without_producer() -> None:
    _, run = run_named_candidate(
        failing=frozenset(
            {
                "Primary",
                "Fallback",
            }
        ),
    )

    with pytest.raises(
        ProductionEmissionError,
        match="Declared production emission was not produced uniquely.",
    ):
        emit_production_result(
            state=create_state(),
            run=run,
        )


def test_promotion_emits_name_only_result() -> None:
    specification = create_workflow().model_copy(
        update={
            "result": NAMED_ANSWER,
        }
    )

    revision = promote_workflow_candidate(
        specification=specification,
        candidate=create_candidate(specification),
        repository=InMemoryWorkflowProductionStateRepository(),
        revision_repository=InMemoryWorkflowProductionRevisionRepository(),
    )

    assert revision.state.specification.result == NAMED_ANSWER

    assert revision.state.emissions == (
        WorkflowProductionEmission(
            name="result",
            source=NAMED_ANSWER,
        ),
    )

    assert PROMPT_STEP_ID in {step.id for step in revision.state.specification.steps}


def test_describe_value_reference_renders_explicit_reference() -> None:
    assert (
        describe_value_reference(
            WorkflowValueReference(
                producer_step_id=PRIMARY_STEP_ID,
                name="answer",
            )
        )
        == f"step {PRIMARY_STEP_ID} output answer"
    )


def test_describe_value_reference_renders_name_only_reference() -> None:
    assert describe_value_reference(NAMED_ANSWER) == "output answer (first producer in step order)"


def test_production_rendering_describes_name_only_emission() -> None:
    rendered = render_workflow_production(
        create_state(),
        active_revision=None,
    )

    assert "Emission: result <- output answer (first producer in step order)" in rendered
