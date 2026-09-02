"""Process-local composition of Azathoth runtime dependencies."""

from uuid import UUID

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.runtime.exceptions import WorkflowNotConfiguredError
from azathoth.tools import (
    ToolCatalog,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowProductionState,
    generate_workflow_candidate,
)


class AzathothRuntime:
    """Compose durable catalogs with process-local runtime implementations."""

    def __init__(
        self,
        *,
        workflows: WorkflowCatalog,
        models: ModelCatalog,
        portfolio: ModelPortfolio,
        language_models: LanguageModelRegistry,
        production_states: tuple[WorkflowProductionState, ...] = (),
        tools: ToolCatalog | None = None,
        tool_implementations: ToolImplementationCatalog | None = None,
    ) -> None:
        self._workflows = workflows

        production_workflow_ids = tuple(
            state.specification.metadata.id for state in production_states
        )

        if len(production_workflow_ids) != len(set(production_workflow_ids)):
            raise ValueError("Runtime production states must contain unique workflow identifiers.")

        self._production_states = production_states

        self._models = models
        self._portfolio = portfolio
        self._language_models = language_models

        self._tools = tools if tools is not None else ToolCatalog()

        self._tool_implementations = (
            tool_implementations
            if tool_implementations is not None
            else ToolImplementationCatalog()
        )

        self._tool_resolver = ToolResolver(self._tools)

        self._tool_implementation_resolver = ToolImplementationResolver(self._tool_implementations)

    @property
    def workflows(self) -> WorkflowCatalog:
        """Return configured durable workflow specifications."""

        return self._workflows

    @property
    def production_states(
        self,
    ) -> tuple[WorkflowProductionState, ...]:
        """Return durable workflow states currently active in production."""

        return self._production_states

    def production_state(
        self,
        workflow_id: UUID,
    ) -> WorkflowProductionState | None:
        """Return active production state for one workflow."""

        return next(
            (
                state
                for state in self._production_states
                if state.specification.metadata.id == workflow_id
            ),
            None,
        )

    @property
    def models(self) -> ModelCatalog:
        """Return configured durable model metadata."""

        return self._models

    @property
    def language_models(self) -> LanguageModelRegistry:
        """Return executable language-model implementations."""

        return self._language_models

    @property
    def tools(self) -> ToolCatalog:
        """Return configured durable tool definitions."""

        return self._tools

    @property
    def tool_implementations(self) -> ToolImplementationCatalog:
        """Return configured durable tool implementations."""

        return self._tool_implementations

    @property
    def tool_resolver(self) -> ToolResolver:
        """Return capability resolution over configured tools."""

        return self._tool_resolver

    @property
    def tool_implementation_resolver(
        self,
    ) -> ToolImplementationResolver:
        """Return implementation resolution over configured tools."""

        return self._tool_implementation_resolver

    @property
    def portfolio(
        self,
    ) -> ModelPortfolio:
        """Return organizational model-selection authorization."""

        return self._portfolio

    def generate_workflow_candidate(
        self,
        workflow_id: UUID,
    ) -> WorkflowCandidate:
        """Generate an executable candidate for one configured workflow."""

        specification = self._workflows.get(workflow_id)

        if specification is None:
            raise WorkflowNotConfiguredError(f"Workflow {workflow_id} is not configured.")

        return generate_workflow_candidate(
            specification=specification,
            catalog=self._models,
            registry=self._language_models,
            portfolio=self._portfolio,
            tool_resolver=self._tool_resolver,
            tool_implementation_resolver=(self._tool_implementation_resolver),
        )
