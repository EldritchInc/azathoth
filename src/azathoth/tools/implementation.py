"""Domain models describing durable tool implementations."""

import re
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

PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE = "AZATHOTH_TOOL_TIMEOUT_SECONDS"
"""The variable that tells a process tool its own timeout, in seconds (ADR 0093)."""

TRACEPARENT_ENVIRONMENT_VARIABLE = "TRACEPARENT"
"""The variable carrying the W3C `traceparent` of the step a process tool runs in (ADR 0100)."""

TRACESTATE_ENVIRONMENT_VARIABLE = "TRACESTATE"
"""The variable carrying the W3C `tracestate` of the step a process tool runs in (ADR 0100)."""

TRACE_CONTEXT_ENVIRONMENT_VARIABLES = (
    TRACEPARENT_ENVIRONMENT_VARIABLE,
    TRACESTATE_ENVIRONMENT_VARIABLE,
)
"""The variables carrying a step's trace context to a process tool."""

LINEAGE_ENVIRONMENT_VARIABLE = "AZATHOTH_LINEAGE"
"""The variable carrying the lineage of the step a process tool runs in (ADR 0104)."""

MANAGED_ENVIRONMENT_VARIABLES = (
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    *TRACE_CONTEXT_ENVIRONMENT_VARIABLES,
    LINEAGE_ENVIRONMENT_VARIABLE,
)
"""The variables the engine sets itself: never inherited, and never grantable."""

ENVIRONMENT_GRANT_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*\*?$"
"""A grant names one variable, or a prefix of names followed by `*` (ADR 0099)."""

ENVIRONMENT_PREFIX_WILDCARD = "*"
"""The suffix that turns a grant into a prefix of variable names."""

_ENVIRONMENT_GRANT = re.compile(ENVIRONMENT_GRANT_PATTERN)

CONTENT_INPUT_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
"""A content input is named as a tool input is: letters, digits and underscores (ADR 0114)."""

_CONTENT_INPUT_NAME = re.compile(CONTENT_INPUT_NAME_PATTERN)

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

    A process implementation may also grant itself environment variables
    beyond the base environment every process tool receives: exact names, or
    prefixes ending in `*` (ADR 0099). An implementation without grants
    serializes without them.

    A process implementation may name some of its inputs content inputs: each
    is given as a file holding the content a handle names, rather than as the
    handle (ADR 0114). An implementation without content inputs serializes
    without them.

    An implementation with content inputs may name an extraction output: the
    output holding what the tool extracted from them, which the engine checks,
    keeps and records, and replaces with a handle naming it (ADR 0114). An
    implementation without one serializes without it.
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

    environment: tuple[str, ...] = ()

    content_inputs: tuple[str, ...] = ()

    extraction_output: str | None = None

    @model_validator(mode="after")
    def validate_extraction_output(self) -> Self:
        """Require a well-formed extraction output, only beside content inputs.

        Raises:
            ValueError: The name is malformed, or the implementation takes no
                content inputs to extract from.
        """

        if self.extraction_output is None:
            return self

        if _CONTENT_INPUT_NAME.fullmatch(self.extraction_output) is None:
            raise ValueError(
                f"Extraction output {self.extraction_output!r} must be a name of letters, "
                "digits and underscores."
            )

        if not self.content_inputs:
            raise ValueError(
                "An extraction output holds what a tool extracted from its content inputs, "
                "so an implementation with one takes at least one content input."
            )

        return self

    @model_validator(mode="after")
    def validate_content_inputs(self) -> Self:
        """Require well-formed, unique content input names, and only on process implementations.

        Raises:
            ValueError: A name is malformed or repeated, or another runtime
                declares content inputs.
        """

        if not self.content_inputs:
            return self

        if self.runtime != PROCESS_TOOL_RUNTIME:
            raise ValueError("Only process tool implementations may take content inputs.")

        for name in self.content_inputs:
            if _CONTENT_INPUT_NAME.fullmatch(name) is None:
                raise ValueError(
                    f"Content input {name!r} must be a name of letters, digits and underscores."
                )

        if len(set(self.content_inputs)) != len(self.content_inputs):
            raise ValueError("Content inputs must be unique.")

        return self

    @model_validator(mode="after")
    def validate_environment_grants(self) -> Self:
        """Require well-formed, unique grants, and only on process implementations.

        Raises:
            ValueError: A grant is malformed, repeated, names a variable the
                engine manages, or is declared by another runtime.
        """

        if not self.environment:
            return self

        if self.runtime != PROCESS_TOOL_RUNTIME:
            raise ValueError("Only process tool implementations may grant environment variables.")

        for grant in self.environment:
            if _ENVIRONMENT_GRANT.fullmatch(grant) is None:
                raise ValueError(
                    f"Environment grant {grant!r} must be a variable name, "
                    "or a prefix of one followed by '*'."
                )

            if grant == PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE:
                raise ValueError(
                    f"{PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE} is set by the engine "
                    "from timeout_seconds and cannot be granted."
                )

            if grant in TRACE_CONTEXT_ENVIRONMENT_VARIABLES:
                raise ValueError(
                    f"{grant} is set by the engine from the active trace and cannot be granted."
                )

            if grant == LINEAGE_ENVIRONMENT_VARIABLE:
                raise ValueError(
                    f"{LINEAGE_ENVIRONMENT_VARIABLE} is set by the engine from the running "
                    "step and cannot be granted."
                )

        if len(set(self.environment)) != len(self.environment):
            raise ValueError("Environment grants must be unique.")

        return self

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

        for name in ("environment", "content_inputs", "extraction_output"):
            if not serialized.get(name):
                serialized.pop(name, None)

        return serialized
