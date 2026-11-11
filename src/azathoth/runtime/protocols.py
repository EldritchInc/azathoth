"""Protocols exposed by Azathoth runtime composition."""

from typing import Protocol
from uuid import UUID

from azathoth.evaluation import (
    JudgeRotation,
    OutcomeEvaluator,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.sensitivity import Sensitivity
from azathoth.tools import (
    ToolCatalog,
    ToolImplementationCatalog,
    ToolImplementationResolver,
    ToolResolver,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
)


class RuntimeEnvironment(Protocol):
    """Expose dependencies and operations required for Azathoth runtime assembly."""

    @property
    def workflows(self) -> WorkflowCatalog:
        """Return configured workflow specifications."""

        ...

    @property
    def models(self) -> ModelCatalog:
        """Return configured model metadata."""

        ...

    @property
    def portfolio(
        self,
    ) -> ModelPortfolio:
        """Return organizational model-selection authorization."""

        ...

    @property
    def language_models(self) -> LanguageModelRegistry:
        """Return executable language-model implementations."""

        ...

    @property
    def tools(self) -> ToolCatalog:
        """Return configured tool definitions."""

        ...

    @property
    def tool_implementations(self) -> ToolImplementationCatalog:
        """Return configured tool implementations."""

        ...

    @property
    def tool_resolver(self) -> ToolResolver:
        """Return capability resolution for configured tools."""

        ...

    @property
    def tool_implementation_resolver(
        self,
    ) -> ToolImplementationResolver:
        """Return implementation resolution for configured tools."""

        ...

    @property
    def judges(
        self,
    ) -> JudgeRotation:
        """Return the durable rotation of semantic judges."""

        ...

    def outcome_evaluator(
        self,
        *,
        semantic: bool = False,
        sensitivity: Sensitivity | None = None,
    ) -> OutcomeEvaluator:
        """Return the evaluator that judges outcomes, with judges allowed to see the label."""

        ...

    def generate_workflow_candidate(
        self,
        workflow_id: UUID,
        *,
        sensitivity: Sensitivity | None = None,
    ) -> WorkflowCandidate:
        """Generate an executable candidate for runs of one configured workflow with a label."""

        ...
