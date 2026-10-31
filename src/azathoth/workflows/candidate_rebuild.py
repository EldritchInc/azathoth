"""Rebuild a recorded workflow candidate from its signature (ADR 0092)."""

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
    ContextPromptStrategySpec,
    PromptSpecification,
    PromptStrategySpec,
    generate_context_prompt_candidates,
    generate_prompt_candidates,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.strategies import Strategy
from azathoth.workflows.candidate import (
    WorkflowCandidate,
    WorkflowCandidateSignature,
    WorkflowCandidateStep,
)
from azathoth.workflows.generation import WorkflowGenerationError
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.steps import ToolStepSpecification


class WorkflowCandidateRebuildError(WorkflowGenerationError):
    """Raised when a recorded candidate signature cannot be rebuilt."""


def rebuild_workflow_candidate(
    *,
    specification: WorkflowSpecification,
    configured: WorkflowCandidate,
    signature: WorkflowCandidateSignature,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    portfolio: ModelPortfolio,
) -> WorkflowCandidate:
    """Rebuild the executable candidate a signature identifies.

    The configured candidate is the workflow's current revision as generated
    for promotion. Each of its steps whose strategy ID matches the signature
    is kept. A prompt step whose ID differs is matched against the candidates
    generated for it over the authorized models, because a generated prompt
    strategy's ID is derived from the step and its model. The rebuilt
    candidate's signature equals the recorded one.

    Raises:
        WorkflowCandidateRebuildError: The signature names another workflow,
            no revision, or another revision; it has a different number of
            steps; or a step cannot be matched, because it is a tool step or
            its model is not currently available and authorized.
    """

    workflow_id = specification.metadata.id

    if configured.metadata.id != workflow_id:
        raise ValueError("Workflow specification and candidate must share an identifier.")

    if signature.workflow_id != workflow_id:
        raise WorkflowCandidateRebuildError(
            f"The candidate was measured on workflow {signature.workflow_id}, "
            f"not workflow {workflow_id}."
        )

    if signature.workflow_revision is None:
        raise WorkflowCandidateRebuildError(
            f"The candidate for workflow {workflow_id} records no workflow revision."
        )

    if signature.workflow_revision != configured.revision:
        raise WorkflowCandidateRebuildError(
            f"The candidate was measured on revision {signature.workflow_revision} of "
            f"workflow {workflow_id}, but its current revision is {configured.revision}."
        )

    if len(signature.strategy_ids) != len(configured.steps):
        raise WorkflowCandidateRebuildError(
            f"The candidate has {len(signature.strategy_ids)} steps, but revision "
            f"{configured.revision} of workflow {workflow_id} has {len(configured.steps)}."
        )

    step_specifications = {step.id: step.specification for step in specification.steps}

    steps = tuple(
        _rebuild_step(
            step=step,
            strategy_id=strategy_id,
            step_specification=step_specifications[step.id],
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
        )
        for step, strategy_id in zip(
            configured.steps,
            signature.strategy_ids,
            strict=True,
        )
    )

    candidate = replace(
        configured,
        steps=steps,
    )

    if candidate.signature != signature:
        raise WorkflowCandidateRebuildError(
            f"The rebuilt candidate for workflow {workflow_id} does not match its signature."
        )

    return candidate


def _rebuild_step(
    *,
    step: WorkflowCandidateStep,
    strategy_id: UUID,
    step_specification: PromptSpecification | ToolStepSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    portfolio: ModelPortfolio,
) -> WorkflowCandidateStep:
    """Return the step bound to the strategy the signature names."""

    if step.strategy.metadata.id == strategy_id:
        return step

    if not isinstance(step_specification, PROMPT_SPECIFICATIONS):
        raise WorkflowCandidateRebuildError(
            f"Workflow step {step.id} is a tool step whose strategy differs from the candidate's."
        )

    strategy = next(
        (
            generated
            for generated in _generated_strategies(
                specification=step_specification,
                catalog=catalog,
                registry=registry,
                portfolio=portfolio,
            )
            if generated.metadata.id == strategy_id
        ),
        None,
    )

    if strategy is None:
        raise WorkflowCandidateRebuildError(
            f"Workflow step {step.id} cannot be rebuilt: the model it was measured on is "
            "not currently available and authorized for it."
        )

    return replace(
        step,
        strategy=strategy,
    )


def _generated_strategies(
    *,
    specification: PromptSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    portfolio: ModelPortfolio,
) -> Sequence[Strategy]:
    """Return every executable strategy the prompt step can currently use."""

    if isinstance(specification, PromptStrategySpec):
        return generate_prompt_candidates(
            specification=specification,
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
        )

    assert isinstance(specification, ContextPromptStrategySpec)

    return generate_context_prompt_candidates(
        specification=specification,
        catalog=catalog,
        registry=registry,
        portfolio=portfolio,
    )
