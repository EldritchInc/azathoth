"""Generate executable workflow candidates from durable specifications."""

from azathoth.prompting import generate_prompt_candidates
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.models import WorkflowSpecification


class WorkflowGenerationError(Exception):
    """Raised when a workflow specification cannot become executable."""


def generate_workflow_candidate(
    specification: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> WorkflowCandidate:
    """Generate one executable workflow candidate.

    Each workflow step is bound independently. The first eligible executable
    prompt candidate is selected for each step while preserving workflow order.

    Combinatorial expansion across all eligible models is intentionally left
    for a future candidate-generation policy.
    """

    executable_steps = []

    for workflow_step in specification.steps:
        candidates = generate_prompt_candidates(
            specification=workflow_step.specification,
            catalog=catalog,
            registry=registry,
        )

        if not candidates:
            raise WorkflowGenerationError(
                "Unable to generate an executable candidate for workflow "
                f"step {workflow_step.id!s} "
                f"({workflow_step.specification.metadata.name!r})."
            )

        executable_steps.append(candidates[0])

    return WorkflowCandidate(
        metadata=specification.metadata,
        steps=tuple(executable_steps),
    )
