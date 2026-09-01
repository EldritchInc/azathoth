"""Reference workflow optimization through cheaper model substitution."""

from azathoth.optimization.candidate_resolution import (
    resolve_workflow_experiment_winner,
)
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
    """Explore cheaper legal model substitutions from empirical winners."""

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
        """Preserve the population and expand only the empirical winner."""

        winner = resolve_workflow_experiment_winner(
            experiment=experiment,
            candidates=candidates,
        )

        specification = self._workflows.get(winner.metadata.id)

        if specification is None:
            raise ValueError(
                "Workflow candidate must reference a configured workflow specification."
            )

        next_candidates = list(candidates)

        seen: set[WorkflowCandidateSignature] = {candidate.signature for candidate in candidates}

        substitutions = generate_model_substitutions(
            specification=specification,
            candidate=winner,
            catalog=self._models,
            portfolio=self._portfolio,
            registry=self._registry,
        )

        for proposal in substitutions:
            if proposal.signature in seen:
                continue

            seen.add(proposal.signature)
            next_candidates.append(proposal)

        return WorkflowOptimizationResult(
            generation=generation,
            previous_experiment=experiment,
            candidates=tuple(next_candidates),
        )
