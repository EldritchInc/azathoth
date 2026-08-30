"""Test helpers for explicitly authorizing synthetic model catalogs."""

from azathoth.optimization import (
    generate_model_substitutions as _generate_model_substitutions,
)
from azathoth.prompting import (
    PromptStrategy,
    PromptStrategySpec,
)
from azathoth.prompting import (
    generate_prompt_candidates as _generate_prompt_candidates,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
    ModelPortfolioEntry,
)
from azathoth.tools import (
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowSpecification,
)
from azathoth.workflows import (
    generate_workflow_candidate as _generate_workflow_candidate,
)


def portfolio_for_catalog(
    catalog: ModelCatalog,
) -> ModelPortfolio:
    """Authorize every model in one deterministic synthetic test catalog."""

    return ModelPortfolio(
        entries=tuple(
            ModelPortfolioEntry(
                provider=model.provider,
                model=model.model,
            )
            for model in catalog.models
        )
    )


def generate_prompt_candidates(
    specification: PromptStrategySpec,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> tuple[PromptStrategy, ...]:
    """Generate prompt candidates with every synthetic catalog model authorized."""

    return _generate_prompt_candidates(
        specification=specification,
        catalog=catalog,
        registry=registry,
        portfolio=portfolio_for_catalog(catalog),
    )


def generate_workflow_candidate(
    specification: WorkflowSpecification,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    *,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
) -> WorkflowCandidate:
    """Generate a workflow candidate with every synthetic catalog model authorized."""

    return _generate_workflow_candidate(
        specification=specification,
        catalog=catalog,
        registry=registry,
        portfolio=portfolio_for_catalog(catalog),
        tool_resolver=tool_resolver,
        tool_implementation_resolver=(tool_implementation_resolver),
    )


def generate_model_substitutions(
    *,
    specification: WorkflowSpecification,
    candidate: WorkflowCandidate,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
) -> tuple[WorkflowCandidate, ...]:
    """Generate substitutions with every synthetic catalog model authorized."""

    return _generate_model_substitutions(
        specification=specification,
        candidate=candidate,
        catalog=catalog,
        portfolio=portfolio_for_catalog(catalog),
        registry=registry,
    )
