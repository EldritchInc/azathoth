"""Domain models describing durable tool implementations."""

from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

PROCESS_TOOL_RUNTIME = "process"
"""The runtime name of tool implementations executed as subprocesses."""

_PROCESS_ONLY_FIELDS = (
    "command",
    "timeout_seconds",
)


class ToolImplementation(BaseModel):
    """Describe a versioned executable implementation of a tool.

    A process implementation declares the command that interprets its
    source, for example `["bash"]` or `["python3"]`, and optionally a timeout.
    Its source is the script that command runs, so the implementation digest
    covers exactly what executes. Other runtimes declare neither field, and
    an implementation that leaves them unset serializes without them, so its
    documents and content digests are unchanged.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    tool_id: UUID
    tool_version: str = Field(min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    runtime: str = Field(min_length=1)
    entrypoint: str = Field(default="run", min_length=1)
    source: str = Field(min_length=1)

    command: tuple[str, ...] | None = Field(
        default=None,
        min_length=1,
    )

    timeout_seconds: float | None = Field(
        default=None,
        gt=0.0,
    )

    @model_validator(mode="after")
    def validate_process_configuration(self) -> Self:
        """Require a command for process implementations, and only for them."""

        if self.runtime == PROCESS_TOOL_RUNTIME:
            if self.command is None:
                raise ValueError("Process tool implementations must declare a command.")

            if any(not argument for argument in self.command):
                raise ValueError("Process tool implementation command arguments cannot be empty.")

            return self

        if self.command is not None or self.timeout_seconds is not None:
            raise ValueError("Only process tool implementations may declare a command or timeout.")

        return self

    @model_serializer(mode="wrap")
    def serialize_without_unset_process_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the implementation, omitting unset process-only fields."""

        serialized: dict[str, Any] = handler(self)

        for name in _PROCESS_ONLY_FIELDS:
            if serialized.get(name) is None:
                serialized.pop(name, None)

        return serialized
