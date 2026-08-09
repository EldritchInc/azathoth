"""Structured values produced by workflow execution."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


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
    """Bind a workflow value to a named downstream step input."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    source: WorkflowValueReference
