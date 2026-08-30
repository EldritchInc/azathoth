"""End-to-end persistence of workflow execution evidence and feedback."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from azathoth.context import Context
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
    SQLiteWorkflowRunFeedbackRepository,
    SQLiteWorkflowRunRepository,
    WorkflowCatalogLoader,
    WorkflowMetadata,
    WorkflowRun,
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
MODEL_NAME = "evidence-test-model"
MODEL_IDENTIFIER = f"{MODEL_PROVIDER}/{MODEL_NAME}"

FEEDBACK_CREATED_AT = datetime(
    2026,
    8,
    18,
    16,
    30,
    tzinfo=UTC,
)


def create_workflow_specification() -> WorkflowSpecification:
    """Create a durable workflow used to produce execution evidence."""

    return WorkflowSpecification(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Production evidence workflow",
            description=("Produce one deterministic output for durable evidence testing."),
            version="1.0.0",
        ),
        steps=(
            WorkflowStepSpecification(
                id=STEP_ID,
                specification=PromptStrategySpec(
                    metadata=StrategyMetadata(
                        id=STRATEGY_ID,
                        name="classify request",
                        description="Classify the supplied request.",
                        version="1.0.0",
                    ),
                    prompt=Prompt(
                        text="Classify the supplied request.",
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
    """Create deterministic model metadata for workflow generation."""

    return ModelCatalog(
        models=(
            ModelMetadata(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                display_name="Evidence Test Model",
                context_window_tokens=8_192,
            ),
        ),
    )


def create_model_registry() -> LanguageModelRegistry:
    """Create the deterministic executable language model registry."""

    return LanguageModelRegistry(
        models={
            MODEL_IDENTIFIER: DeterministicLanguageModel(
                provider=MODEL_PROVIDER,
                model=MODEL_NAME,
                response_text="positive",
            ),
        },
    )


def persist_workflow(
    database: Path,
) -> None:
    """Persist the workflow specification before execution."""

    SQLiteWorkflowRepository(database).save(create_workflow_specification())


def load_workflow(
    database: Path,
) -> WorkflowSpecification:
    """Reconstruct one workflow specification from durable storage."""

    catalog = WorkflowCatalogLoader(SQLiteWorkflowRepository(database)).load_catalog()

    specification = catalog.get(WORKFLOW_ID)

    assert specification is not None

    return specification


def execute_persisted_workflow(
    database: Path,
) -> WorkflowRun:
    """Reconstruct and execute the persisted workflow."""

    specification = load_workflow(database)

    candidate = generate_workflow_candidate(
        specification=specification,
        catalog=create_model_catalog(),
        registry=create_model_registry(),
    )

    return asyncio.run(
        WorkflowRunner().run(
            candidate,
            Context(),
        )
    )


def create_bad_feedback(
    run: WorkflowRun,
) -> WorkflowRunFeedback:
    """Create deterministic corrective feedback for one completed run."""

    return WorkflowRunFeedback(
        id=FEEDBACK_ID,
        run_id=run.id,
        disposition=WorkflowRunFeedbackDisposition.BAD,
        reason=("The classification should have been negative for this production request."),
        corrected_output="negative",
        created_at=FEEDBACK_CREATED_AT,
    )


def test_persisted_execution_and_feedback_survive_reconstruction(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    original_serialized_run = run.model_dump_json()

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    reconstructed_run_repository = SQLiteWorkflowRunRepository(evidence_database)

    restored_run = reconstructed_run_repository.get(run.id)

    assert restored_run is not None
    assert restored_run == run
    assert restored_run is not run

    feedback = create_bad_feedback(restored_run)

    SQLiteWorkflowRunFeedbackRepository(evidence_database).save(feedback)

    final_run_repository = SQLiteWorkflowRunRepository(evidence_database)

    final_feedback_repository = SQLiteWorkflowRunFeedbackRepository(evidence_database)

    final_run = final_run_repository.get(run.id)

    restored_feedback = final_feedback_repository.feedback_for_run(run.id)

    assert final_run is not None

    assert final_run == run
    assert final_run.model_dump_json() == original_serialized_run

    assert restored_feedback == (feedback,)

    assert restored_feedback[0].run_id == final_run.id

    assert restored_feedback[0].disposition is WorkflowRunFeedbackDisposition.BAD

    assert restored_feedback[0].reason == (
        "The classification should have been negative for this production request."
    )

    assert restored_feedback[0].corrected_output == "negative"


def test_feedback_does_not_modify_raw_execution_evidence(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    run_repository = SQLiteWorkflowRunRepository(evidence_database)

    run_repository.save(run)

    before_feedback = run_repository.get(run.id)

    assert before_feedback is not None

    feedback_repository = SQLiteWorkflowRunFeedbackRepository(evidence_database)

    feedback_repository.save(create_bad_feedback(before_feedback))

    after_feedback = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    assert after_feedback is not None

    assert after_feedback == before_feedback

    assert after_feedback.id == before_feedback.id
    assert after_feedback.workflow == before_feedback.workflow
    assert after_feedback.steps == before_feedback.steps
    assert after_feedback.initial_context == before_feedback.initial_context
    assert after_feedback.final_context == before_feedback.final_context
    assert after_feedback.started_at == before_feedback.started_at
    assert after_feedback.completed_at == before_feedback.completed_at


def test_production_feedback_is_queryable_from_durable_run_identity(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    SQLiteWorkflowRunFeedbackRepository(evidence_database).save(create_bad_feedback(run))

    restored_run = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    feedback = SQLiteWorkflowRunFeedbackRepository(evidence_database).feedback_for_run(run.id)

    assert restored_run is not None
    assert restored_run.id == run.id

    assert len(feedback) == 1
    assert feedback[0].run_id == restored_run.id


def test_reconstructed_run_retains_executable_observation(
    tmp_path: Path,
) -> None:
    workflow_database = tmp_path / "workflows.db"
    evidence_database = tmp_path / "evidence.db"

    persist_workflow(workflow_database)

    run = execute_persisted_workflow(workflow_database)

    SQLiteWorkflowRunRepository(evidence_database).save(run)

    restored = SQLiteWorkflowRunRepository(evidence_database).get(run.id)

    assert restored is not None

    assert restored.workflow.id == WORKFLOW_ID
    assert len(restored.steps) == 1

    step = restored.steps[0]

    assert step.step_id == STEP_ID
    assert step.execution is not None
    assert step.execution.output == "positive"

    assert len(step.attempts) == 1
    assert step.attempts[0].execution == step.execution

    values = restored.values_named("classification")

    assert len(values) == 1
    assert values[0].producer_step_id == STEP_ID
    assert values[0].value == "positive"

    assert restored.succeeded
