"""Process-local composition of Azathoth runtime dependencies."""

from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.tools import (
    ToolCatalog,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows import WorkflowCatalog


class AzathothRuntime:
    """Compose durable catalogs with process-local runtime implementations."""

    def __init__(
        self,
        *,
        workflows: WorkflowCatalog,
        models: ModelCatalog,
        language_models: LanguageModelRegistry,
        tools: ToolCatalog | None = None,
        tool_implementations: ToolImplementationCatalog | None = None,
    ) -> None:
        self._workflows = workflows
        self._models = models
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
    def workflows(
        self,
    ) -> WorkflowCatalog:
        """Return configured durable workflow specifications."""

        return self._workflows

    @property
    def models(
        self,
    ) -> ModelCatalog:
        """Return configured durable model metadata."""

        return self._models

    @property
    def language_models(
        self,
    ) -> LanguageModelRegistry:
        """Return executable language-model implementations."""

        return self._language_models

    @property
    def tools(
        self,
    ) -> ToolCatalog:
        """Return configured durable tool definitions."""

        return self._tools

    @property
    def tool_implementations(
        self,
    ) -> ToolImplementationCatalog:
        """Return configured durable tool implementations."""

        return self._tool_implementations

    @property
    def tool_resolver(
        self,
    ) -> ToolResolver:
        """Return capability resolution over configured tools."""

        return self._tool_resolver

    @property
    def tool_implementation_resolver(
        self,
    ) -> ToolImplementationResolver:
        """Return implementation resolution over configured tools."""

        return self._tool_implementation_resolver
