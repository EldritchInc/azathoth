"""Models describing completed Azathoth strategy executions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from azathoth.context import Context
from azathoth.strategies import StrategyExecutionMetrics


class ExecutionResult(BaseModel):
    """The complete recorded result of executing one strategy."""

    model_config = ConfigDict(frozen=True)

    strategy_id: UUID
    strategy_name: str
    strategy_version: str
    output: JsonValue
    metrics: StrategyExecutionMetrics | None = None
    initial_context: Context
    final_context: Context
    started_at: datetime
    completed_at: datetime
