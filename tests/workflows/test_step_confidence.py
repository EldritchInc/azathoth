"""Tests for declaring and recording step confidence (ADR 0098)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.context import Context
from azathoth.execution import ExecutionResult
from azathoth.revisions import content_digest
from azathoth.tools import ToolRequirement
from azathoth.workflows import (
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    ToolStepSpecification,
    WorkflowCandidate,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepAttempt,
    WorkflowStepConfidenceError,
    WorkflowStepFailure,
    WorkflowStepRun,
    WorkflowStepSpecification,
    WorkflowStepStatus,
    WorkflowValueBinding,
    decode_workflow_document,
    encode_workflow_document,
    generate_production_workflow_candidate,
    generate_workflow_candidate,
    step_confidence,
)
from tests.cli.test_workflow_run import (
    create_runtime,
    create_workflow,
)
from tests.workflows.test_production_execution import (
    create_catalog,
    create_registry,
    create_state,
)

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOW_EXAMPLES = PROJECT_ROOT / "examples" / "workflows"

STEP_ID = UUID("b3000000-0000-4000-8000-000000000011")

STRATEGY_ID = UUID("b3000000-0000-4000-8000-000000000021")

STARTED_AT = datetime(2026, 10, 31, 21, 0, tzinfo=UTC)

COMPLETED_AT = datetime(2026, 10, 31, 21, 0, 1, tzinfo=UTC)

CLASSIFIER_OUTPUTS = (
    WorkflowValueBinding(name="category", path=("category",)),
    WorkflowValueBinding(name="confidence", path=("confidence",)),
)

#
# Digests of the checked-in workflow examples computed before steps could
# declare confidence. An undeclared confidence must never change them.
#
EXAMPLE_DIGESTS = {
    "classify-sentiment.json": "7798b7c4977eec125c49bac1f41a491d1e2ef6d3d40ba0d2e0047fe9c3c15f4e",
    "redundant-word-count.json": "5a7b3500ab70bb4bbcb1c10e67db329d308e840594a411bba8df803941315cb9",
    "simple-prompt.json": "7782dc067a693bd8dbf9785fef6fe48030bab9ad9a3197c5695b60d718823577",
}


def create_step(
    *,
    confidence: str | None = "confidence",
    outputs: tuple[WorkflowValueBinding, ...] = CLASSIFIER_OUTPUTS,
) -> WorkflowStepSpecification:
    """Create one tool step that may declare a confidence."""

    return WorkflowStepSpecification(
        id=STEP_ID,
        specification=ToolStepSpecification(
            requirement=ToolRequirement(
                name="classify",
                version="1.0.0",
                runtime="python",
            ),
        ),
        outputs=outputs,
        confidence=confidence,
    )


def execution_result() -> ExecutionResult:
    """Create one successful strategy execution."""

    return ExecutionResult(
        strategy_id=STRATEGY_ID,
        strategy_name="classify",
        strategy_version="1.0.0",
        output={"category": "billing", "confidence": 0.62},
        initial_context=Context(),
        final_context=Context(),
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )


def executed_run(
    *,
    confidence: float | None,
) -> WorkflowStepRun:
    """Create one executed step run with a confidence."""

    execution = execution_result()

    return WorkflowStepRun(
        step_id=STEP_ID,
        layer_index=0,
        execution=execution,
        attempts=(
            WorkflowStepAttempt(
                attempt_number=1,
                started_at=STARTED_AT,
                completed_at=COMPLETED_AT,
                execution=execution,
            ),
        ),
        confidence=confidence,
    )


# Reading a confidence


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (1, 1.0),
        (0.0, 0.0),
        (1.0, 1.0),
        (0.62, 0.62),
    ],
)
def test_a_number_from_0_to_1_is_a_confidence(
    value: JsonValue,
    expected: float,
) -> None:
    confidence = step_confidence(STEP_ID, "confidence", value)

    assert confidence == expected
    assert isinstance(confidence, float)


@pytest.mark.parametrize(
    ("value", "described"),
    [
        (1.5, "1.5"),
        (-0.1, "-0.1"),
        (2, "2"),
        (62, "62"),
        ("0.9", '"0.9"'),
        (True, "true"),
        (False, "false"),
        (None, "null"),
        ([0.5], "[0.5]"),
        ({"value": 0.5}, '{"value": 0.5}'),
    ],
)
def test_anything_else_is_refused_naming_the_step_and_output(
    value: JsonValue,
    described: str,
) -> None:
    with pytest.raises(WorkflowStepConfidenceError) as raised:
        step_confidence(STEP_ID, "confidence", value)

    assert str(raised.value) == (
        f"Workflow step {STEP_ID} confidence 'confidence' must be a number from 0 to 1; "
        f"got {described}."
    )


def test_the_confidence_error_is_a_value_error() -> None:
    assert issubclass(WorkflowStepConfidenceError, ValueError)


def test_the_bounds_are_0_and_1() -> None:
    assert (MIN_CONFIDENCE, MAX_CONFIDENCE) == (0.0, 1.0)


# Declaring a confidence


def test_a_step_declares_no_confidence_by_default() -> None:
    assert create_step(confidence=None).confidence is None


def test_a_step_names_one_of_its_outputs_as_its_confidence() -> None:
    assert create_step().confidence == "confidence"


def test_any_declared_output_may_be_the_confidence() -> None:
    outputs = (
        WorkflowValueBinding(name="category", path=("category",)),
        WorkflowValueBinding(name="certainty", path=("scores", "certainty")),
    )

    assert create_step(confidence="certainty", outputs=outputs).confidence == "certainty"


def test_a_confidence_must_name_a_declared_output() -> None:
    with pytest.raises(
        ValidationError,
        match=(
            f"Workflow step {STEP_ID} declares confidence 'certainty', "
            "which is not one of its declared outputs\\."
        ),
    ):
        create_step(confidence="certainty")


def test_a_step_without_outputs_cannot_declare_a_confidence() -> None:
    with pytest.raises(ValidationError, match="not one of its declared outputs"):
        create_step(outputs=())


def test_a_confidence_name_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        create_step(confidence="")


def test_an_undeclared_confidence_is_omitted_from_serialization() -> None:
    assert "confidence" not in create_step(confidence=None).model_dump(mode="json")


def test_a_declared_confidence_is_serialized() -> None:
    assert create_step().model_dump(mode="json")["confidence"] == "confidence"


def test_a_step_with_a_confidence_round_trips_through_json() -> None:
    step = create_step()

    assert WorkflowStepSpecification.model_validate_json(step.model_dump_json()) == step


def test_a_step_from_before_confidence_still_decodes() -> None:
    document = json.loads(create_step().model_dump_json())

    del document["confidence"]

    assert WorkflowStepSpecification.model_validate(document).confidence is None


def test_confidence_is_part_of_step_content_identity() -> None:
    assert content_digest(create_step()) != content_digest(create_step(confidence=None))


def test_existing_workflow_example_digests_are_unchanged() -> None:
    for name, expected in EXAMPLE_DIGESTS.items():
        specification = decode_workflow_document(
            (WORKFLOW_EXAMPLES / name).read_text(encoding="utf-8"),
        )

        assert content_digest(specification) == expected, name


def test_a_workflow_document_round_trips_a_step_confidence() -> None:
    specification = create_workflow()

    step = specification.steps[0]

    confident = specification.model_copy(
        update={
            "steps": (
                WorkflowStepSpecification.model_validate(
                    {
                        **step.model_dump(),
                        "outputs": CLASSIFIER_OUTPUTS,
                        "confidence": "confidence",
                    }
                ),
            ),
        }
    )

    decoded = decode_workflow_document(encode_workflow_document(confident))

    assert decoded.steps[0].confidence == "confidence"
    assert decoded == confident


# Generated candidates


def with_confidence(
    specification: WorkflowSpecification,
) -> WorkflowSpecification:
    """Return the workflow with its first step declaring a confidence."""

    step = specification.steps[0]

    return specification.model_copy(
        update={
            "steps": (
                WorkflowStepSpecification.model_validate(
                    {
                        **step.model_dump(),
                        "outputs": CLASSIFIER_OUTPUTS,
                        "confidence": "confidence",
                    }
                ),
                *specification.steps[1:],
            ),
        }
    )


def generate_configured(
    specification: WorkflowSpecification,
) -> WorkflowCandidate:
    """Generate a configured candidate against the CLI run test runtime."""

    runtime = create_runtime()

    return generate_workflow_candidate(
        specification=specification,
        catalog=runtime.models,
        registry=runtime.language_models,
        portfolio=runtime.portfolio,
    )


def generate_production(
    state: WorkflowProductionState,
) -> WorkflowCandidate:
    """Generate a production candidate against the production test models."""

    return generate_production_workflow_candidate(
        state=state,
        catalog=create_catalog(),
        registry=create_registry(),
    )


def test_a_configured_candidate_carries_the_step_confidence() -> None:
    candidate = generate_configured(with_confidence(create_workflow()))

    assert candidate.steps[0].confidence == "confidence"


def test_a_configured_candidate_of_a_step_without_confidence_has_none() -> None:
    assert generate_configured(create_workflow()).steps[0].confidence is None


def test_a_production_candidate_carries_the_step_confidence() -> None:
    state = create_state()

    candidate = generate_production(
        state.model_copy(
            update={"specification": with_confidence(state.specification)},
        )
    )

    assert candidate.steps[0].confidence == "confidence"


def test_a_production_candidate_of_a_step_without_confidence_has_none() -> None:
    assert generate_production(create_state()).steps[0].confidence is None


# Recorded step runs


def test_a_step_run_records_no_confidence_by_default() -> None:
    assert executed_run(confidence=None).confidence is None


@pytest.mark.parametrize("confidence", [0.0, 0.62, 1.0])
def test_an_executed_step_run_records_its_confidence(
    confidence: float,
) -> None:
    assert executed_run(confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_a_recorded_confidence_stays_from_0_to_1(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        executed_run(confidence=confidence)


def test_a_skipped_step_records_no_confidence() -> None:
    with pytest.raises(ValidationError, match="Skipped workflow steps cannot record a confidence"):
        WorkflowStepRun(
            step_id=STEP_ID,
            layer_index=0,
            status=WorkflowStepStatus.SKIPPED,
            confidence=0.5,
        )


def test_a_failed_step_records_no_confidence() -> None:
    with pytest.raises(ValidationError, match="Failed workflow steps cannot record a confidence"):
        WorkflowStepRun(
            step_id=STEP_ID,
            layer_index=0,
            status=WorkflowStepStatus.FAILED,
            attempts=(
                WorkflowStepAttempt(
                    attempt_number=1,
                    started_at=STARTED_AT,
                    completed_at=COMPLETED_AT,
                    failure=WorkflowStepFailure(
                        exception_type="WorkflowStepConfidenceError",
                        message="No confidence.",
                    ),
                ),
            ),
            confidence=0.5,
        )


def test_a_step_run_round_trips_its_confidence() -> None:
    run = executed_run(confidence=0.62)

    assert WorkflowStepRun.model_validate_json(run.model_dump_json()) == run


def test_a_step_run_recorded_before_confidence_still_loads() -> None:
    document = json.loads(executed_run(confidence=None).model_dump_json())

    del document["confidence"]

    assert WorkflowStepRun.model_validate(document).confidence is None
