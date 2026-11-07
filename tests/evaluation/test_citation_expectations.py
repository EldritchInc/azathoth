"""Tests that a case names what its run must cite, and compares results by what they cite."""

import asyncio
from typing import Any

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.evaluation import (
    CHECK_KEYS,
    CITED_KEYS,
    CitationExpectation,
    CitedSegment,
    ExpectedOutcome,
    OutcomeComparison,
    OutcomeEvaluator,
    compared_value,
    is_cited,
)

CHECK: dict[str, JsonValue] = {
    "source": "claim",
    "segment": "p1.s2",
    "quote": "December 14",
    "status": "verified",
    "anchor": {"digest": "a" * 64, "selectors": []},
}

NATIVE: dict[str, JsonValue] = {
    "source": "claim",
    "segment": None,
    "quote": "March 3.",
    "status": "quote_not_found",
    "supports": "on March 3",
    "pages": [1, 2],
}


def test_an_outcome_without_citations_serializes_as_it_always_has() -> None:
    outcome = ExpectedOutcome(description="d", value=1, comparison=OutcomeComparison.EXACT)

    assert outcome.model_dump(mode="json") == {
        "description": "d",
        "value": 1,
        "comparison": "exact",
    }


def test_an_outcome_with_citations_round_trips_them() -> None:
    outcome = ExpectedOutcome.model_validate(
        {
            "description": "d",
            "value": 1,
            "comparison": "exact",
            "citations": {"require": [{"source": "claim", "segment": "p1.s2"}]},
        }
    )

    assert outcome.citations == CitationExpectation(
        require=(CitedSegment(source="claim", segment="p1.s2"),),
        on_unverified="fail",
    )
    assert ExpectedOutcome.model_validate(outcome.model_dump(mode="json")) == outcome


def test_an_expectation_requires_nothing_and_fails_unverified_citations_by_default() -> None:
    assert CitationExpectation() == CitationExpectation(require=(), on_unverified="fail")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"on_unverified": "warn"}, id="unknown-policy"),
        pytest.param({"require": [{"source": "claim"}]}, id="no-segment"),
        pytest.param({"require": [{"source": "", "segment": "p1"}]}, id="empty-source"),
        pytest.param({"require": [{"source": "c", "segment": "p1", "quote": "q"}]}, id="quote"),
        pytest.param({"minimum": 1}, id="extra-key"),
    ],
)
def test_an_expectation_is_validated(
    value: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        CitationExpectation.model_validate(value)


def test_a_segment_required_twice_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        CitationExpectation.model_validate(
            {
                "require": [
                    {"source": "claim", "segment": "p1.s2"},
                    {"source": "claim", "segment": "p1.s2"},
                ]
            }
        )

    assert raised.value.errors()[0]["msg"] == (
        "Value error, Citation expectation requires segment p1.s2 of source 'claim' more than once."
    )


def test_the_keys_of_citations_and_checks() -> None:
    assert {"source", "segment", "quote"} == CITED_KEYS
    assert CITED_KEYS | {"status", "anchor", "supports", "pages"} == CHECK_KEYS


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"source": "claim", "segment": "p1.s2", "quote": "x"}, id="citation"),
        pytest.param(CHECK, id="check"),
        pytest.param(NATIVE, id="native-check"),
    ],
)
def test_citations_and_checks_compare_as_the_segment_they_cite(
    value: JsonValue,
) -> None:
    assert is_cited(value)

    assert isinstance(value, dict)
    assert compared_value(value) == {"source": "claim", "segment": value["segment"]}


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"source": "claim", "segment": "p1.s2"}, id="no-quote"),
        pytest.param({**CHECK, "page": 1}, id="another-key"),
        pytest.param({**CHECK, "quote": 14}, id="quote-not-a-string"),
        pytest.param({**CHECK, "source": None}, id="source-not-a-string"),
        pytest.param({**CHECK, "segment": 2}, id="segment-not-a-string"),
        pytest.param(["claim", "p1.s2", "x"], id="a-list"),
    ],
)
def test_values_that_only_look_like_citations_compare_as_they_are(
    value: JsonValue,
) -> None:
    assert not is_cited(value)
    assert compared_value(value) == (
        value if not isinstance(value, dict) else {key: value[key] for key in value}
    )


def test_citations_compare_wherever_they_stand() -> None:
    assert compared_value(
        {"claims": [{"received": "December 14", "support": [CHECK, NATIVE]}], "n": 1}
    ) == {
        "claims": [
            {
                "received": "December 14",
                "support": [
                    {"source": "claim", "segment": "p1.s2"},
                    {"source": "claim", "segment": None},
                ],
            }
        ],
        "n": 1,
    }


@pytest.mark.parametrize(
    "comparison",
    [OutcomeComparison.EXACT, OutcomeComparison.NORMALIZED],
)
def test_an_outcome_compares_results_by_what_they_cite(
    comparison: OutcomeComparison,
) -> None:
    expected = ExpectedOutcome(
        description="d",
        value={"received": "December 14", "citations": [{**CHECK, "quote": "Dec 14"}]},
        comparison=comparison,
    )

    evaluation = asyncio.run(
        OutcomeEvaluator().evaluate(expected, {"received": "December 14", "citations": [CHECK]})
    )

    assert evaluation.passed


def test_a_result_citing_another_segment_does_not_compare_equal() -> None:
    expected = ExpectedOutcome(
        description="d",
        value={"citations": [{"source": "claim", "segment": "p2.s1"}]},
        comparison=OutcomeComparison.EXACT,
    )

    assert not asyncio.run(OutcomeEvaluator().evaluate(expected, {"citations": [CHECK]})).passed


def test_a_schema_validates_the_result_as_it_is() -> None:
    expected = ExpectedOutcome(
        description="d",
        value={
            "type": "object",
            "properties": {
                "citations": {
                    "type": "array",
                    "items": {
                        "required": ["status"],
                        "properties": {"status": {"const": "verified"}},
                    },
                }
            },
        },
        comparison=OutcomeComparison.SCHEMA,
    )

    assert asyncio.run(OutcomeEvaluator().evaluate(expected, {"citations": [CHECK]})).passed
