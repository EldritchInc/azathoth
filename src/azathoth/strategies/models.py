"""Domain models shared by executable Azathoth strategies."""

from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from azathoth.context import ContextEvent
from azathoth.costs import CostBasis, cost_basis_of, require_cost_for_basis


class StrategyMetadata(BaseModel):
    """Stable identifying information for an executable strategy."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class StrategyResourceBinding(BaseModel):
    """Describe one durable resource bound to strategy execution."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    identifier: str = Field(min_length=1)
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
    )


class StrategyExecutionMetrics(BaseModel):
    """Provider-neutral measurements produced during strategy execution.

    `cost_basis` says how `estimated_cost_usd` is known, as the model's
    reply said; metrics stored before 1.5 have none, and
    `known_cost_basis` reads it from their provider (ADR 0132).
    """

    model_config = ConfigDict(frozen=True)

    provider: str | None = None
    model: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    cost_basis: CostBasis | None = None

    @property
    def known_cost_basis(self) -> CostBasis | None:
        """Return how the cost is known: its own basis, or else its provider's."""

        return cost_basis_of(self.provider, self.estimated_cost_usd, self.cost_basis)

    @model_validator(mode="after")
    def validate_cost_basis(self) -> "StrategyExecutionMetrics":
        """Refuse a basis for metrics with no cost."""

        require_cost_for_basis(self.estimated_cost_usd, self.cost_basis)

        return self

    @model_validator(mode="after")
    def validate_total_tokens(self) -> "StrategyExecutionMetrics":
        """Ensure total tokens agree with known prompt and completion usage."""

        if (
            self.prompt_tokens is not None
            and self.completion_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.prompt_tokens + self.completion_tokens
        ):
            raise ValueError("Total tokens must equal prompt tokens plus completion tokens.")

        return self


class StrategyOutcome(BaseModel):
    """The direct output produced by a strategy implementation."""

    model_config = ConfigDict(frozen=True)

    output: JsonValue
    events: tuple[ContextEvent, ...] = ()
    resources: tuple[StrategyResourceBinding, ...] = ()
    metrics: StrategyExecutionMetrics | None = None
