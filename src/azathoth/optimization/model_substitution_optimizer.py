"""Reference workflow optimization through cheaper model substitution."""

from uuid import UUID

from azathoth.optimization.model_substitution import (
    generate_model_substitutions,
)
from azathoth.optimization.workflow import (
    WorkflowOptimizationResult,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCatalog,
    WorkflowExperimentResult,
)


class ModelSubstitutionWorkflowOptimizer:
    """Generate cheaper legal model substitutions for workflow candidates."""

    def __init__(
        self,
        *,
        workflows: WorkflowCatalog,
        models: ModelCatalog,
        registry: LanguageModelRegistry,
    ) -> None:
        self._workflows = workflows
        self._models = models
        self._registry = registry

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Preserve the population and add unique cheaper substitutions."""

        next_candidates: list[WorkflowCandidate] = []
        seen: set[tuple[UUID, ...]] = set()

        for candidate in candidates:
            specification = self._workflows.get(candidate.metadata.id)

            if specification is None:
                raise ValueError(
                    "Workflow candidate must reference a configured workflow specification."
                )

            proposals = (
                candidate,
                *generate_model_substitutions(
                    specification=specification,
                    candidate=candidate,
                    catalog=self._models,
                    registry=self._registry,
                ),
            )

            for proposal in proposals:
                signature = tuple(step.strategy.metadata.id for step in proposal.steps)

                if signature in seen:
                    continue

                seen.add(signature)
                next_candidates.append(proposal)

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=tuple(next_candidates),
        )
