"""Tests for the W3C Web Annotation selectors a source anchor holds (ADR 0113)."""

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from azathoth.citations import (
    FRAGMENT_SPECIFICATIONS,
    MEDIA_FRAGMENT_SPECIFICATION,
    PDF_FRAGMENT_SPECIFICATION,
    FragmentSelector,
    Selector,
    TextPositionSelector,
    TextQuoteSelector,
)


class Holder(BaseModel):
    """A model holding one selector of any kind, as a source anchor does."""

    selector: Selector


def test_the_fragment_specifications_are_the_ones_the_w3c_model_lists() -> None:
    assert PDF_FRAGMENT_SPECIFICATION == "http://tools.ietf.org/rfc/rfc3778"
    assert MEDIA_FRAGMENT_SPECIFICATION == "http://www.w3.org/TR/media-frags/"
    assert (
        frozenset({PDF_FRAGMENT_SPECIFICATION, MEDIA_FRAGMENT_SPECIFICATION})
        == FRAGMENT_SPECIFICATIONS
    )


def test_a_quote_selector_dumps_with_w3c_names() -> None:
    selector = TextQuoteSelector(exact="received on December 14", prefix="was ", suffix=", 2026")

    assert selector.model_dump(mode="json") == {
        "type": "TextQuoteSelector",
        "exact": "received on December 14",
        "prefix": "was ",
        "suffix": ", 2026",
    }


def test_a_quote_selector_without_context_dumps_empty_context() -> None:
    assert TextQuoteSelector(exact="Claim").model_dump(mode="json") == {
        "type": "TextQuoteSelector",
        "exact": "Claim",
        "prefix": "",
        "suffix": "",
    }


def test_a_position_selector_dumps_with_w3c_names() -> None:
    assert TextPositionSelector(start=4, end=7).model_dump(mode="json") == {
        "type": "TextPositionSelector",
        "start": 4,
        "end": 7,
    }


def test_a_fragment_selector_dumps_conforms_to_in_camel_case() -> None:
    selector = FragmentSelector(value="page=3", conformsTo=PDF_FRAGMENT_SPECIFICATION)

    assert selector.model_dump(mode="json") == {
        "type": "FragmentSelector",
        "value": "page=3",
        "conformsTo": "http://tools.ietf.org/rfc/rfc3778",
    }


@pytest.mark.parametrize(
    ("model", "fields", "message"),
    [
        pytest.param(
            TextQuoteSelector,
            {"exact": ""},
            "A TextQuoteSelector's exact text is never empty.",
            id="empty-quote",
        ),
        pytest.param(
            TextPositionSelector,
            {"start": -1, "end": 3},
            "greater than or equal to 0",
            id="negative-start",
        ),
        pytest.param(
            TextPositionSelector,
            {"start": 7, "end": 7},
            "A TextPositionSelector's end comes after its start; got start 7 and end 7.",
            id="empty-span",
        ),
        pytest.param(
            TextPositionSelector,
            {"start": 9, "end": 4},
            "A TextPositionSelector's end comes after its start; got start 9 and end 4.",
            id="reversed-span",
        ),
        pytest.param(
            FragmentSelector,
            {"value": "#page=3", "conformsTo": PDF_FRAGMENT_SPECIFICATION},
            "A FragmentSelector's value is a fragment without its '#'; got '#page=3'.",
            id="leading-hash",
        ),
        pytest.param(
            FragmentSelector,
            {"value": "", "conformsTo": PDF_FRAGMENT_SPECIFICATION},
            "A FragmentSelector's value is a fragment without its '#'; got ''.",
            id="empty-value",
        ),
        pytest.param(
            FragmentSelector,
            {"value": "line=3", "conformsTo": "http://tools.ietf.org/rfc/rfc5147"},
            "A FragmentSelector conforms to http://tools.ietf.org/rfc/rfc3778 or "
            "http://www.w3.org/TR/media-frags/; got 'http://tools.ietf.org/rfc/rfc5147'.",
            id="other-specification",
        ),
        pytest.param(
            TextQuoteSelector,
            {"exact": "Claim", "type": "TextPositionSelector"},
            "Input should be 'TextQuoteSelector'",
            id="wrong-type",
        ),
        pytest.param(
            TextPositionSelector,
            {"start": 0, "end": 1, "refinedBy": {}},
            "Extra inputs are not permitted",
            id="extra-field",
        ),
    ],
)
def test_selectors_are_validated(
    model: type[BaseModel],
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        model.model_validate(fields)

    assert message in str(raised.value)


@pytest.mark.parametrize(
    "selector",
    [
        TextQuoteSelector(exact="received", prefix="was ", suffix=" on"),
        TextPositionSelector(start=18234, end=18257),
        FragmentSelector(value="xywh=160,120,320,240", conformsTo=MEDIA_FRAGMENT_SPECIFICATION),
    ],
)
def test_a_selector_reads_back_by_its_type(
    selector: TextQuoteSelector | TextPositionSelector | FragmentSelector,
) -> None:
    dumped = Holder(selector=selector).model_dump(mode="json")

    assert Holder.model_validate(dumped).selector == selector


def test_an_unknown_selector_type_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        Holder.model_validate({"selector": {"type": "XPathSelector", "value": "/html/body"}})

    assert "XPathSelector" in str(raised.value)


def test_selectors_are_frozen() -> None:
    selector = TextPositionSelector(start=0, end=1)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        selector.__setattr__("end", 2)
