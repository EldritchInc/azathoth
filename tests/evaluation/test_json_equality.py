"""Tests for type-strict JSON value comparison."""

import pytest
from pydantic import JsonValue

from azathoth.evaluation import (
    JsonDifference,
    first_json_difference,
    json_type_name,
    json_values_equal,
)


@pytest.mark.parametrize(
    ("value", "type_name"),
    (
        (None, "null"),
        (True, "boolean"),
        (False, "boolean"),
        (0, "number"),
        (1.5, "number"),
        ("text", "string"),
        ([1, 2], "array"),
        ({"key": "value"}, "object"),
    ),
)
def test_json_type_name(
    value: JsonValue,
    type_name: str,
) -> None:
    assert json_type_name(value) == type_name


@pytest.mark.parametrize(
    ("expected", "actual"),
    (
        (None, None),
        (True, True),
        (1, 1),
        (1, 1.0),
        (0.5, 0.5),
        ("label", "label"),
        ([1, "two", None], [1, "two", None]),
        ({"a": 1, "b": [True]}, {"b": [True], "a": 1}),
    ),
)
def test_equal_json_values(
    expected: JsonValue,
    actual: JsonValue,
) -> None:
    assert json_values_equal(expected, actual)
    assert first_json_difference(expected, actual) is None


@pytest.mark.parametrize(
    ("expected", "actual"),
    (
        (1, True),
        (True, 1),
        (0, False),
        (False, 0),
        (1.0, True),
    ),
)
def test_booleans_never_equal_numbers(
    expected: JsonValue,
    actual: JsonValue,
) -> None:
    assert not json_values_equal(expected, actual)

    assert first_json_difference(expected, actual) == JsonDifference(
        path="$",
        expected_type=json_type_name(expected),
        actual_type=json_type_name(actual),
    )


def test_null_never_equals_falsy_values() -> None:
    assert not json_values_equal(None, False)
    assert not json_values_equal(None, 0)
    assert not json_values_equal(None, "")
    assert not json_values_equal(None, [])
    assert not json_values_equal(None, {})


def test_difference_reports_nested_object_path() -> None:
    assert first_json_difference(
        {"result": {"approved": 1}},
        {"result": {"approved": True}},
    ) == JsonDifference(
        path="$.result.approved",
        expected_type="number",
        actual_type="boolean",
    )


def test_difference_reports_array_index_path() -> None:
    assert first_json_difference(
        {"labels": ["a", "b", "c"]},
        {"labels": ["a", "x", "c"]},
    ) == JsonDifference(
        path="$.labels[1]",
        expected_type="string",
        actual_type="string",
    )


def test_difference_reports_array_length_mismatch_at_array() -> None:
    assert first_json_difference(
        {"labels": ["a", "b"]},
        {"labels": ["a"]},
    ) == JsonDifference(
        path="$.labels",
        expected_type="array",
        actual_type="array",
    )


def test_difference_reports_object_key_mismatch_at_object() -> None:
    assert first_json_difference(
        {"a": 1, "b": 2},
        {"a": 1, "c": 2},
    ) == JsonDifference(
        path="$",
        expected_type="object",
        actual_type="object",
    )


def test_array_order_matters() -> None:
    assert not json_values_equal([1, 2], [2, 1])


def test_first_difference_follows_sorted_keys() -> None:
    difference = first_json_difference(
        {"b": 1, "a": 1},
        {"b": 2, "a": 2},
    )

    assert difference is not None
    assert difference.path == "$.a"
