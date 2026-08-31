"""Reference workflow optimization through cheaper model substitution."""

from azathoth.optimization.model_substitution import (
    generate_model_substitutions,
)
from azathoth.optimization.workflow import (
    WorkflowOptimizationResult,
)
from azathoth.providers import (
    LanguageModelRegistry,
    ModelCatalog,
    ModelPortfolio,
)
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowCandidateSignature,
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
        portfolio: ModelPortfolio,
        registry: LanguageModelRegistry,
    ) -> None:
        self._workflows = workflows
        self._models = models
        self._registry = registry
        self._portfolio = portfolio

    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult:
        """Preserve the population and add unique cheaper substitutions."""

        next_candidates: list[WorkflowCandidate] = []
        seen: set[WorkflowCandidateSignature] = set()

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
                    portfolio=self._portfolio,
                    registry=self._registry,
                ),
            )

            for proposal in proposals:
                if proposal.signature in seen:
                    continue

                seen.add(proposal.signature)
                next_candidates.append(proposal)

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=tuple(next_candidates),
        )
