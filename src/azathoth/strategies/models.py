"""Domain models shared by executable Azathoth strategies."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from azathoth.context import ContextEvent


class StrategyMetadata(BaseModel):
    """Stable identifying information for an executable strategy."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)


class StrategyExecutionMetrics(BaseModel):
    """Provider-neutral measurements produced during strategy execution."""

    model_config = ConfigDict(frozen=True)

    provider: str | None = None
    model: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)

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
    metrics: StrategyExecutionMetrics | None = None
