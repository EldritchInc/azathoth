"""Materialize executable workflow candidates as durable promotion specifications."""

from azathoth.prompting import (
    FixedModelSelection,
    PromptStrategy,
)
from azathoth.strategies import Strategy
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.steps import (
    ToolStepSpecification,
    WorkflowStepSpecification,
)


def materialize_workflow_candidate(
    *,
    specification: WorkflowSpecification,
    candidate: WorkflowCandidate,
) -> WorkflowSpecification:
    """Materialize one executable workflow candidate as durable configuration."""

    if specification.metadata.id != candidate.metadata.id:
        raise ValueError("Workflow specification and candidate must share an identifier.")

    candidate_steps = {step.id: step for step in candidate.steps}

    specification_step_ids = {step.id for step in specification.steps}

    if set(candidate_steps) != specification_step_ids:
        raise ValueError(
            "Workflow specification and candidate must contain the same step identifiers."
        )

    promoted_steps = tuple(
        _materialize_step(
            specification=workflow_step,
            candidate_strategy=candidate_steps[workflow_step.id].strategy,
        )
        for workflow_step in specification.steps
    )

    return specification.model_copy(
        update={
            "steps": promoted_steps,
        }
    )


def _materialize_step(
    *,
    specification: WorkflowStepSpecification,
    candidate_strategy: Strategy,
) -> WorkflowStepSpecification:
    """Materialize one executable candidate step as durable configuration."""

    step_specification = specification.specification

    if isinstance(
        step_specification,
        ToolStepSpecification,
    ):
        return specification

    if not isinstance(
        candidate_strategy,
        PromptStrategy,
    ):
        raise ValueError("Prompt-backed workflow steps must use PromptStrategy candidates.")

    model_binding = candidate_strategy.model_binding

    if model_binding is None:
        raise ValueError("Prompt-backed workflow candidates must retain model bindings.")

    provider, separator, model = model_binding.identifier.partition("/")

    if not separator or not provider or not model:
        raise ValueError(
            "Prompt-backed workflow candidate model bindings must use "
            "provider-qualified identifiers."
        )

    promoted_prompt = step_specification.model_copy(
        update={
            "model_selection": FixedModelSelection(
                provider=provider,
                model=model,
            ),
        }
    )

    return specification.model_copy(
        update={
            "specification": promoted_prompt,
        }
    )
