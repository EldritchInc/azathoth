"""Structured values produced by workflow execution."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class WorkflowValue(BaseModel):
    """A structured value produced by a workflow step."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: JsonValue
    producer_step_id: UUID


class WorkflowValueReference(BaseModel):
    """Identify a workflow value produced by a specific workflow step."""

    model_config = ConfigDict(frozen=True)

    producer_step_id: UUID
    name: str = Field(min_length=1)


class WorkflowNamedValueReference(BaseModel):
    """Identify a workflow value by name alone among redundant producers.

    A step input written as `{"name": "address"}` resolves among the steps it
    depends on that declare an output with this name. The first of them, in
    workflow step order, that actually produced the value supplies it, so a
    redundant producer that was skipped or failed under a tolerant policy is
    passed over reproducibly.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str = Field(min_length=1)


WorkflowResultReference = WorkflowValueReference | WorkflowNamedValueReference
"""Reference a workflow's declared result explicitly or by name alone."""


class WorkflowContextReference(BaseModel):
    """Identify a field in the latest matching execution context event."""

    model_config = ConfigDict(frozen=True)

    event_type: str = Field(min_length=1)
    field_name: str = Field(min_length=1)


class WorkflowConstantValue(BaseModel):
    """A constant JSON value bound to a step input (ADR 0094).

    Written `{"value": <JSON>}` in a workflow document. Any JSON value may be
    the constant, including objects, lists and null.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    value: JsonValue


class WorkflowInputResolutionError(RuntimeError):
    """Raised when an eligible step has no value to bind to one of its inputs.

    The runner records the step as failed under its own failure policy
    instead of aborting the run, because a redundant or tolerated upstream
    failure can legitimately leave an input without a value.
    """


class WorkflowValueResolutionError(ValueError):
    """Raised when a workflow value binding cannot resolve an output path."""


class WorkflowValueBinding(BaseModel):
    """Declare a named value exported from a workflow step output."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    path: tuple[str | int, ...] = ()

    def resolve(self, output: JsonValue) -> JsonValue:
        """Resolve this binding against a strategy output."""

        value: JsonValue = output

        for segment in self.path:
            if isinstance(segment, str):
                if not isinstance(value, dict) or segment not in value:
                    raise WorkflowValueResolutionError(
                        f"Cannot resolve workflow value {self.name!r}: "
                        f"missing object key {segment!r}."
                    )

                value = value[segment]
                continue

            if not isinstance(value, list):
                raise WorkflowValueResolutionError(
                    f"Cannot resolve workflow value {self.name!r}: "
                    f"expected a list for index {segment}."
                )

            try:
                value = value[segment]
            except IndexError as error:
                raise WorkflowValueResolutionError(
                    f"Cannot resolve workflow value {self.name!r}: "
                    f"list index {segment} is out of range."
                ) from error

        return value


class WorkflowInputBinding(BaseModel):
    """Bind a workflow value, a context value or a constant to a named step input."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    source: (
        WorkflowValueReference
        | WorkflowNamedValueReference
        | WorkflowContextReference
        | WorkflowConstantValue
    )

    @model_validator(mode="before")
    @classmethod
    def reject_constant_with_other_keys(
        cls,
        data: Any,
    ) -> Any:
        """Reject a source that carries a constant value beside other keys.

        A reference that ignores unknown keys would otherwise accept such a
        source and silently drop its value.

        Raises:
            ValueError: The source has a `value` key and any other key.
        """

        if isinstance(data, dict):
            source = data.get("source")

            if isinstance(source, dict) and "value" in source and len(source) > 1:
                raise ValueError("A constant input source holds only 'value'.")

        return data
