"""JSON Schema validation shared by expected outcomes and evaluators."""

from collections.abc import Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class JsonSchemaViolation(BaseModel):
    """One location where a JSON value violates a JSON Schema."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    message: str = Field(min_length=1)


def json_schema_validator(
    schema: JsonValue,
) -> Validator:
    """Return a validator for one checked JSON Schema.

    The schema dialect follows its `$schema` keyword and defaults to Draft
    2020-12. Schemas must be objects or booleans, and object schemas must
    satisfy their dialect's metaschema. Boolean schemas are always valid:
    `true` accepts every value and `false` rejects every value.

    Raises:
        ValueError: The schema is not a valid JSON Schema.
    """

    if isinstance(schema, bool):
        return Draft202012Validator(schema)

    if not isinstance(schema, dict):
        raise ValueError("A JSON Schema must be an object or a boolean.")

    validator_class = validator_for(
        schema,
        default=Draft202012Validator,
    )

    try:
        validator_class.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"Invalid JSON Schema: {error.message}") from error

    return validator_class(schema)


def json_schema_violations(
    validator: Validator,
    instance: JsonValue,
) -> tuple[JsonSchemaViolation, ...]:
    """Return every schema violation of one value in deterministic order."""

    violations = (
        JsonSchemaViolation(
            path=render_json_path(error.absolute_path),
            message=error.message,
        )
        for error in validator.iter_errors(instance)
    )

    return tuple(
        sorted(
            violations,
            key=lambda violation: (violation.path, violation.message),
        )
    )


def render_json_path(
    parts: Iterable[str | int],
) -> str:
    """Render JSON Schema error path parts as a `$`-rooted JSON path."""

    return "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in parts)
