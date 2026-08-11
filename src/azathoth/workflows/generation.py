"""Generate executable workflow candidates."""

from azathoth.prompting import generate_prompt_candidates
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateStep,
)
from azathoth.workflows.models import WorkflowSpecification


class WorkflowGenerationError(Exception):
    """Raised when a workflow specification cannot become executable."""


def generate_workflow_candidate(
    specification: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Generate one executable candidate from a workflow specification."""

    executable_steps: list[WorkflowCandidateStep] = []

    for workflow_step in specification.steps:
        prompt_candidates = generate_prompt_candidates(
            specification=workflow_step.specification,
            catalog=catalog,
            registry=registry,
        )

        if not prompt_candidates:
            raise WorkflowGenerationError(
                "No executable prompt candidate could be generated for "
                f"workflow step {workflow_step.id}."
            )

        executable_steps.append(
            WorkflowCandidateStep(
                id=workflow_step.id,
                strategy=prompt_candidates[0],
                depends_on=workflow_step.depends_on,
                inputs=workflow_step.inputs,
                outputs=workflow_step.outputs,
                conditions=workflow_step.conditions,
                retry_policy=workflow_step.retry_policy,
            )
        )

    return WorkflowCandidate(
        metadata=specification.metadata,
        steps=tuple(executable_steps),
    )
