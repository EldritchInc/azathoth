"""Type-strict JSON value comparison shared by evaluators."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ROOT_PATH = "$"


class JsonDifference(BaseModel):
    """Locate the first point where two JSON values differ."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    expected_type: str = Field(min_length=1)
    actual_type: str = Field(min_length=1)


def json_type_name(
    value: JsonValue,
) -> str:
    """Return the JSON type name of one value."""

    if value is None:
        return "null"

    if isinstance(value, bool):
        return "boolean"

    if isinstance(value, int | float):
        return "number"

    if isinstance(value, str):
        return "string"

    if isinstance(value, list):
        return "array"

    return "object"


def first_json_difference(
    expected: JsonValue,
    actual: JsonValue,
    *,
    path: str = ROOT_PATH,
) -> JsonDifference | None:
    """Return the first difference between two JSON values, if any.

    Comparison follows JSON types rather than Python equality: booleans are
    never numbers, numbers compare by value regardless of integer or decimal
    form, arrays compare in order, and objects require identical keys.
    """

    expected_type = json_type_name(expected)
    actual_type = json_type_name(actual)

    difference = JsonDifference(
        path=path,
        expected_type=expected_type,
        actual_type=actual_type,
    )

    if expected_type != actual_type:
        return difference

    if isinstance(expected, list):
        assert isinstance(actual, list)

        if len(expected) != len(actual):
            return difference

        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True),
        ):
            item_difference = first_json_difference(
                expected_item,
                actual_item,
                path=f"{path}[{index}]",
            )

            if item_difference is not None:
                return item_difference

        return None

    if isinstance(expected, dict):
        assert isinstance(actual, dict)

        if set(expected) != set(actual):
            return difference

        for key in sorted(expected):
            item_difference = first_json_difference(
                expected[key],
                actual[key],
                path=f"{path}.{key}",
            )

            if item_difference is not None:
                return item_difference

        return None

    return None if expected == actual else difference


def json_values_equal(
    expected: JsonValue,
    actual: JsonValue,
) -> bool:
    """Return whether two JSON values are equal under JSON typing."""

    return first_json_difference(expected, actual) is None
