"""Generate executable candidates from durable production workflow state."""

from azathoth.prompting import (
    PROMPT_SPECIFICATIONS,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.sensitivity import Sensitivity
from azathoth.tools import (
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.generation import generate_workflow_candidate
from azathoth.workflows.models import WorkflowSpecification
from azathoth.workflows.production import WorkflowProductionState
from azathoth.workflows.production_model_resolution import (
    resolve_production_model_selection,
)
from azathoth.workflows.steps import WorkflowStepSpecification


def generate_production_workflow_candidate(
    *,
    state: WorkflowProductionState,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
    portfolio: ModelPortfolio | None = None,
    sensitivity: Sensitivity | None = None,
) -> WorkflowCandidate:
    """Generate one executable candidate using production model authority.

    The candidate carries the promoted specification revision, so production
    runs name the revision they execute.

    Production chooses its models from the production state, never from the
    portfolio. The portfolio, as it is when the invocation runs, supplies
    only each model's declared data policy: without one, no model may
    receive restricted input. For an invocation labelled `sensitivity`, each
    context prompt step runs on the first approved model that may receive
    it, if there is one (ADR 0123).
    """

    policies = portfolio if portfolio is not None else ModelPortfolio()

    specification = _resolve_production_specification(
        state=state,
        catalog=catalog,
        registry=registry,
        portfolio=policies,
        sensitivity=sensitivity,
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
        portfolio=policies,
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
        revision=state.specification_revision,
    )


def _resolve_production_specification(
    *,
    state: WorkflowProductionState,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    portfolio: ModelPortfolio,
    sensitivity: Sensitivity | None,
) -> WorkflowSpecification:
    """Resolve production prompt steps to their executable fixed models."""

    steps = tuple(
        _resolve_production_step(
            state=state,
            step=step,
            catalog=catalog,
            registry=registry,
            portfolio=portfolio,
            sensitivity=sensitivity,
        )
        for step in state.specification.steps
    )

    return state.specification.model_copy(
        update={
            "steps": steps,
        }
    )


def _resolve_production_step(
    *,
    state: WorkflowProductionState,
    step: WorkflowStepSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    portfolio: ModelPortfolio,
    sensitivity: Sensitivity | None,
) -> WorkflowStepSpecification:
    """Resolve one production prompt step while preserving all other state.

    Fixed and context prompts are resolved alike: each runs on its primary
    model when that model is executable, and otherwise on its first
    executable approved substitute.
    """

    specification = step.specification

    if not isinstance(
        specification,
        PROMPT_SPECIFICATIONS,
    ):
        return step

    selection = resolve_production_model_selection(
        state=state,
        step_id=step.id,
        catalog=catalog,
        registry=registry,
        portfolio=portfolio,
        sensitivity=sensitivity,
    )

    resolved_prompt = specification.model_copy(
        update={
            "model_selection": selection,
        }
    )

    return step.model_copy(
        update={
            "specification": resolved_prompt,
        }
    )
