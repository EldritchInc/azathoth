"""End-to-end persistence of workflow execution, evaluation, and feedback."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
from azathoth.evaluation import (
    EvaluationStatus,
    ExactMatchEvaluator,
    ExpectedOutcome,
    OutcomeComparison,
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
    SQLiteWorkflowRepository,
    SQLiteWorkflowRunEvaluationRepository,
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCatalogLoader,
    WorkflowMetadata,
    WorkflowRun,
    WorkflowRunEvaluation,
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
    WorkflowRunner,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
)
from tests.model_authorization import (
    generate_workflow_candidate,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
FEEDBACK_ID = UUID("44444444-4444-4444-4444-444444444444")

MODEL_PROVIDER = "deterministic"
MODEL_NAME = "evaluation-evidence-model"
MODEL_IDENTIFIER = f"{MODEL_PROVIDER}/{MODEL_NAME}"

EVALUATED_AT = datetime(
    2026,
    8,
    19,
    20,
    0,
    tzinfo=UTC,
)

FEEDBACK_CREATED_AT = datetime(
    2026,
    8,
    19,
    20,
    1,
    tzinfo=UTC,
)


def create_workflow_specification() -> WorkflowSpecification:
    """Create the durable workflow used by the evidence test."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Evaluation evidence workflow",
            description=("Produce deterministic output for durable evaluation evidence."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="classify request",
                        description="Return a deterministic classification.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the request.",
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


def create_model_catalog() -> ModelCatalog:
    """Create deterministic model metadata."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                display_name="Evaluation Evidence Model",
                context_window_tokens=8_192,
            ),
        ),
    )


def create_model_registry() -> LanguageModelRegistry:
    """Create the deterministic executable model registry."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                response_text="positive",
            ),
        },
    )


def create_expected_outcome() -> ExpectedOutcome:
    """Create an expectation that intentionally fails."""

    return ExpectedOutcome(
        description="The request should be classified as negative.",
        value="negative",
        comparison=OutcomeComparison.EXACT,
    )


def persist_workflow(
    database: Path,
) -> None:
    """Persist the workflow before execution."""

    SQLiteWorkflowRepository(database).save(create_workflow_specification())


def load_workflow(
    database: Path,
) -> WorkflowSpecification:
    """Reconstruct the persisted workflow specification."""

    catalog = WorkflowCatalogLoader(SQLiteWorkflowRepository(database)).load_catalog()

    specification = catalog.get(WORKFLOW_ID)

    assert specification is not None

    return specification


def execute_persisted_workflow(
    database: Path,
) -> WorkflowRun:
    """Reconstruct and execute the persisted workflow."""

    candidate = generate_workflow_candidate(
        specification=load_workflow(database),
        catalog=create_model_catalog(),
        registry=create_model_registry(),
    )

    return asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )


def evaluate_run(
    run: WorkflowRun,
) -> WorkflowRunEvaluation:
    """Evaluate the recorded output and associate it with the run."""

    values = run.values_named("classification")

    assert len(values) == 1

    evaluation = asyncio.run(
        ExactMatchEvaluator().evaluate(
            expected=create_expected_outcome(),
            actual=values[0].value,
        )
    )

    return WorkflowRunEvaluation(
        run_id=run.id,
        evaluation=evaluation,
        evaluated_at=EVALUATED_AT,
    )


def create_feedback(
    run: WorkflowRun,
) -> WorkflowRunFeedback:
    """Create independent human/application judgment for the run."""

    return WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=run.id,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason="The production classification was incorrect.",
        corrected_output="negative",
        created_at=FEEDBACK_CREATED_AT,
    )


def test_run_evaluation_survives_complete_evidence_reconstruction(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    original_serialized_run = run.model_dump_json()

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    reconstructed_run = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    assert reconstructed_run is not None

    run_evaluation = evaluate_run(reconstructed_run)

    SQLiteWorkflowRunEvaluationRepository(evidence_database).save(run_evaluation)

    final_run = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    restored_evaluations = SQLiteWorkflowRunEvaluationRepository(
        evidence_database
    ).evaluations_for_run(run.id)

    assert final_run is not None

    assert final_run == run
    assert final_run.model_dump_json() == original_serialized_run

    assert restored_evaluations == (run_evaluation,)

    restored_evaluation = restored_evaluations[0]

    assert restored_evaluation.run_id == final_run.id

    assert restored_evaluation.id == restored_evaluation.evaluation.id

    assert restored_evaluation.evaluation.status is EvaluationStatus.FAILED

    assert restored_evaluation.evaluation.score == 0.0
    assert restored_evaluation.evaluation.threshold == 1.0
    assert not restored_evaluation.evaluation.passed


def test_evaluator_evidence_preserves_expected_and_actual_outputs(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    run_evaluation = evaluate_run(run)

    SQLiteWorkflowRunEvaluationRepository(evidence_database).save(run_evaluation)

    restored = SQLiteWorkflowRunEvaluationRepository(evidence_database).get(run_evaluation.id)

    assert restored is not None

    evidence = restored.evaluation.evidence

    assert len(evidence) == 2

    assert evidence[0].label == "expected"
    assert evidence[0].value == "negative"

    assert evidence[1].label == "actual"
    assert evidence[1].value == "positive"


def test_machine_evaluation_and_human_feedback_coexist_for_run(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    original_serialized_run = run.model_dump_json()

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    run_evaluation = evaluate_run(run)

    feedback = create_feedback(run)

    SQLiteWorkflowRunEvaluationRepository(evidence_database).save(run_evaluation)

    SQLiteWorkflowRunFeedbackRepository(evidence_database).save(feedback)

    final_run = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    evaluations = SQLiteWorkflowRunEvaluationRepository(evidence_database).evaluations_for_run(
        run.id
    )

    feedback_records = SQLiteWorkflowRunFeedbackRepository(evidence_database).feedback_for_run(
        run.id
    )

    assert final_run is not None

    assert final_run.model_dump_json() == original_serialized_run

    assert evaluations == (run_evaluation,)

    assert feedback_records == (feedback,)

    assert evaluations[0].evaluation.status is EvaluationStatus.FAILED

    assert feedback_records[0].disposition is WorkflowRunFeedbackDisposition.BAD

    assert evaluations[0].run_id == final_run.id
    assert feedback_records[0].run_id == final_run.id


def test_machine_and_human_judgments_remain_independent(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    run_repository = SQLiteWorkflowRunRepository(evidence_database)
    evaluation_repository = SQLiteWorkflowRunEvaluationRepository(evidence_database)
    feedback_repository = SQLiteWorkflowRunFeedbackRepository(evidence_database)

    run_repository.save(run)

    run_evaluation = evaluate_run(run)

    feedback = WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=run.id,
        disposition=WorkflowRunFeedbackDisposition.GOOD,
        reason=("The observed classification is acceptable for this production request."),
        created_at=FEEDBACK_CREATED_AT,
    )

    evaluation_repository.save(run_evaluation)
    feedback_repository.save(feedback)

    restored_evaluation = SQLiteWorkflowRunEvaluationRepository(
        evidence_database
    ).evaluations_for_run(run.id)[0]

    restored_feedback = SQLiteWorkflowRunFeedbackRepository(evidence_database).feedback_for_run(
        run.id
    )[0]

    assert restored_evaluation.evaluation.status is EvaluationStatus.FAILED

    assert restored_feedback.disposition is WorkflowRunFeedbackDisposition.GOOD

    assert restored_evaluation.run_id == restored_feedback.run_id
