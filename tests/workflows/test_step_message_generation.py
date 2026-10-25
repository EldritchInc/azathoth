"""Tests that generated candidates carry step messages and value emission."""

from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
    WorkflowValueBinding,
    generate_production_workflow_candidate,
    generate_workflow_candidate,
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

MESSAGE = "Counting words"

ANSWER_OUTPUT = (
    WorkflowValueBinding(
        name="answer",
    ),
)


def announce(
    step: WorkflowStepSpecification,
) -> WorkflowStepSpecification:
    """Return the step with a message, declared output, and value emission."""

    return WorkflowStepSpecification.model_validate(
        {
            **step.model_dump(),
            "outputs": ANSWER_OUTPUT,
            "message": MESSAGE,
            "emit_values": True,
        }
    )


def announce_workflow(
    specification: WorkflowSpecification,
) -> WorkflowSpecification:
    """Return the workflow with every step announced."""

    return specification.model_copy(
        update={
            "steps": tuple(announce(step) for step in specification.steps),
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


def test_configured_candidate_carries_step_message_and_value_emission() -> None:
    candidate = generate_configured(
        announce_workflow(create_workflow()),
    )

    assert candidate.steps[0].message == MESSAGE
    assert candidate.steps[0].emit_values is True


def test_configured_candidate_of_silent_step_is_silent() -> None:
    candidate = generate_configured(
        create_workflow(),
    )

    assert candidate.steps[0].message is None
    assert candidate.steps[0].emit_values is False


def test_production_candidate_carries_step_message_and_value_emission() -> None:
    state = create_state()

    candidate = generate_production(
        state.model_copy(
            update={
                "specification": announce_workflow(state.specification),
            }
        )
    )

    assert candidate.steps[0].message == MESSAGE
    assert candidate.steps[0].emit_values is True


def test_production_candidate_of_silent_step_is_silent() -> None:
    candidate = generate_production(
        create_state(),
    )

    assert candidate.steps[0].message is None
    assert candidate.steps[0].emit_values is False
