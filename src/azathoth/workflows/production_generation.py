"""Generate executable candidates from durable production workflow state."""

from azathoth.prompting import PromptStrategySpec
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
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
) -> WorkflowCandidate:
    """Generate one executable candidate using production model authority."""

    specification = _resolve_production_specification(
        state=state,
        catalog=catalog,
        registry=registry,
    )

    return generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
        portfolio=ModelPortfolio(),
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
    )


def _resolve_production_specification(
    *,
    state: WorkflowProductionState,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> WorkflowSpecification:
    """Resolve production prompt steps to their executable fixed models."""

    steps = tuple(
        _resolve_production_step(
            state=state,
            step=step,
            catalog=catalog,
            registry=registry,
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
) -> WorkflowStepSpecification:
    """Resolve one production prompt step while preserving all other state."""

    specification = step.specification

    if not isinstance(
        specification,
        PromptStrategySpec,
    ):
        return step

    selection = resolve_production_model_selection(
        state=state,
        step_id=step.id,
        catalog=catalog,
        registry=registry,
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
