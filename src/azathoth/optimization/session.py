"""Workflow optimization session models."""

from collections import Counter

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    model_validator,
)

from azathoth.optimization.candidate_resolution import (
    resolve_workflow_experiment_winner,
)
from azathoth.optimization.workflow import WorkflowOptimizationResult
from azathoth.workflows.candidate import WorkflowCandidate
from azathoth.workflows.experiment import WorkflowExperimentResult


class WorkflowOptimizationSession(BaseModel):
    """Record the generations produced during workflow optimization.

    Each generation holds the experiment that measured one population and the
    population proposed from its winner. The final evaluation is the
    experiment that measured the last generation's population (ADR 0091). It
    is absent when that population held no candidate the last experiment had
    not already evaluated.
    """

    model_config = ConfigDict(
        frozen=True,
    )

    initial_candidates: tuple[
        InstanceOf[WorkflowCandidate],
        ...,
    ] = Field(
        min_length=1,
    )

    generations: tuple[WorkflowOptimizationResult, ...] = ()

    final_experiment: WorkflowExperimentResult | None = None

    @model_validator(mode="after")
    def validate_generation_sequence(self) -> "WorkflowOptimizationSession":
        """Ensure optimization generations are consecutive starting at one."""

        actual_generations = tuple(generation.generation for generation in self.generations)
        expected_generations = tuple(
            range(
                1,
                len(self.generations) + 1,
            )
        )

        if actual_generations != expected_generations:
            raise ValueError("Workflow optimization generations must be consecutive starting at 1.")

        return self

    @model_validator(mode="after")
    def validate_final_experiment(self) -> "WorkflowOptimizationSession":
        """Ensure the final evaluation measured exactly the final population.

        Raises:
            ValueError: The session has a final evaluation but no generation,
                or the final evaluation did not evaluate exactly the last
                generation's candidates.
        """

        if self.final_experiment is None:
            return self

        if not self.generations:
            raise ValueError(
                "A workflow optimization final evaluation requires at least one generation."
            )

        evaluated = Counter(
            evidence.candidate_signature for evidence in self.final_experiment.evidence
        )
        proposed = Counter(candidate.signature for candidate in self.final_population)

        if evaluated != proposed:
            raise ValueError(
                "A workflow optimization final evaluation must evaluate exactly "
                "the last generation's candidates."
            )

        return self

    @property
    def final_population(self) -> tuple[WorkflowCandidate, ...]:
        """Return the last proposed population, or the initial one before any generation."""

        if not self.generations:
            return self.initial_candidates

        return self.generations[-1].candidates

    @property
    def winning_experiment(self) -> WorkflowExperimentResult | None:
        """Return the experiment whose winner is the session's winner.

        This is the final evaluation when there is one, and the last
        generation's experiment otherwise. A session with no generation has
        measured nothing, so it has no winning experiment.
        """

        if self.final_experiment is not None:
            return self.final_experiment

        if not self.generations:
            return None

        return self.generations[-1].previous_experiment

    @property
    def winning_population(self) -> tuple[WorkflowCandidate, ...]:
        """Return the candidates the winning experiment evaluated.

        Empty when the session has no winning experiment.
        """

        if self.final_experiment is not None:
            return self.final_population

        if not self.generations:
            return ()

        if len(self.generations) == 1:
            return self.initial_candidates

        return self.generations[-2].candidates

    @property
    def winner(self) -> WorkflowCandidate | None:
        """Return the session's winning candidate, or `None` before any generation."""

        experiment = self.winning_experiment

        if experiment is None:
            return None

        return resolve_workflow_experiment_winner(
            experiment=experiment,
            candidates=self.winning_population,
        )
