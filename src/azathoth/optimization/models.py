"""Domain models used to define Azathoth optimization jobs."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from azathoth.context import Context
from azathoth.evaluation import EvaluationResult, ExpectedOutcome
from azathoth.execution import ExecutionResult
from azathoth.goals import Goal
from azathoth.strategies import StrategyMetadata


class OptimizationExample(BaseModel):
    """A reproducible example of a goal, context, and expected result."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    goal: Goal
    context: Context
    expected_outcome: ExpectedOutcome
    tags: tuple[str, ...] = ()


class OptimizationRun(BaseModel):
    """The complete result of executing and evaluating one strategy."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    example_id: UUID
    execution: ExecutionResult
    evaluation: EvaluationResult
    started_at: datetime
    completed_at: datetime

    @model_validator(mode="after")
    def validate_completion_time(self) -> "OptimizationRun":
        """Ensure the run does not complete before it starts."""

        if self.completed_at < self.started_at:
            raise ValueError("Optimization run cannot complete before it starts.")

        return self

    @property
    def passed(self) -> bool:
        """Return whether the evaluated strategy run passed."""

        return self.evaluation.passed


class StrategyScorecard(BaseModel):
    """Aggregated optimization evidence for one candidate strategy."""

    model_config = ConfigDict(frozen=True)

    strategy: StrategyMetadata
    runs: tuple[OptimizationRun, ...] = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def run_count(self) -> int:
        """Return the number of evaluated runs in this scorecard."""

        return len(self.runs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed_count(self) -> int:
        """Return the number of runs that passed evaluation."""

        return sum(run.passed for run in self.runs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pass_rate(self) -> float:
        """Return the proportion of runs that passed."""

        return self.passed_count / self.run_count

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mean_score(self) -> float:
        """Return the arithmetic mean of all evaluation scores."""

        return sum(run.evaluation.score for run in self.runs) / self.run_count

    @model_validator(mode="after")
    def validate_strategy_identity(self) -> "StrategyScorecard":
        """Ensure every run belongs to the scorecard's strategy."""

        mismatched_runs = tuple(
            run
            for run in self.runs
            if (
                run.execution.strategy_id != self.strategy.id
                or run.execution.strategy_name != self.strategy.name
                or run.execution.strategy_version != self.strategy.version
            )
        )

        if mismatched_runs:
            raise ValueError("Every optimization run must belong to the scorecard strategy.")

        return self


class RankedStrategy(BaseModel):
    """A strategy scorecard assigned a deterministic rank."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    scorecard: StrategyScorecard


class StrategyRanking(BaseModel):
    """An ordered comparison of candidate strategy scorecards."""

    model_config = ConfigDict(frozen=True)

    entries: tuple[RankedStrategy, ...] = Field(min_length=1)

    @property
    def winner(self) -> StrategyScorecard:
        """Return the highest-ranked strategy scorecard."""

        return self.entries[0].scorecard

    @model_validator(mode="after")
    def validate_rank_order(self) -> "StrategyRanking":
        """Ensure ranking positions are consecutive and ordered."""

        expected_ranks = tuple(range(1, len(self.entries) + 1))
        actual_ranks = tuple(entry.rank for entry in self.entries)

        if actual_ranks != expected_ranks:
            raise ValueError("Strategy ranking entries must use consecutive ranks starting at 1.")

        return self
