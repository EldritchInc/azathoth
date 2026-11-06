"""Tests for the standard text segmenter (ADR 0113)."""

import re
from pathlib import Path

import pytest

from azathoth.citations import (
    TEXT_SEGMENTER,
    TEXT_SEGMENTER_VERSION,
    CitationCheck,
    CitationStatus,
    Segment,
    SegmentedText,
    segment_text,
    verify_citation,
)
from azathoth.inputs import InMemoryContentStore, content_bytes_digest

TEXT = "Claim 0412.\n\nThe claim was\nreceived on December 14.\n\n\n  Late, twice.  \n"

SOURCE = content_bytes_digest(TEXT.encode("utf-8"))


def segmented(
    text: str = TEXT,
    media_type: str = "text/plain",
) -> SegmentedText:
    """Return the test text, segmented."""

    return segment_text(text, source_digest=SOURCE, media_type=media_type)


def spans(
    text: SegmentedText,
) -> list[str]:
    """Return the text of each segment."""

    return [text.segment_text(segment) for segment in text.segments]


def test_the_segmenter_names_itself_and_its_own_version() -> None:
    assert (TEXT_SEGMENTER, TEXT_SEGMENTER_VERSION) == ("segment_text", "1")

    result = segmented()

    assert (result.tool, result.version) == ("segment_text", "1")
    assert (result.source_digest, result.media_type) == (SOURCE, "text/plain")


def test_each_paragraph_is_one_segment_without_its_surrounding_whitespace() -> None:
    result = segmented()

    assert spans(result) == [
        "Claim 0412.",
        "The claim was\nreceived on December 14.",
        "Late, twice.",
    ]
    assert [segment.id for segment in result.segments] == ["s1", "s2", "s3"]


def test_segments_count_positions_in_the_whole_text() -> None:
    result = segmented()

    assert result.text == TEXT
    assert result.segments[1] == Segment(
        id="s2",
        start=TEXT.index("The claim"),
        end=TEXT.index("14.") + 3,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("One.\n \t \nTwo.", ["One.", "Two."], id="blank-line-of-spaces"),
        pytest.param("One.\r\n\r\nTwo.", ["One.", "Two."], id="windows-line-endings"),
        pytest.param("One.\nTwo.", ["One.\nTwo."], id="single-line-break"),
        pytest.param("One.\u2029Two.", ["One.\u2029Two."], id="paragraph-separator-kept"),
        pytest.param("\n\n\nOne.\n\n\n\n", ["One."], id="blank-lines-around"),
    ],
)
def test_paragraphs_are_separated_by_blank_lines(
    text: str,
    expected: list[str],
) -> None:
    assert spans(segmented(text)) == expected


@pytest.mark.parametrize("text", ["", " ", "\n\n\t\n"])
def test_text_with_nothing_in_it_has_no_segments(
    text: str,
) -> None:
    assert segmented(text).segments == ()


def test_text_is_normalized_to_nfc_before_it_is_counted() -> None:
    result = segmented("Cafe\u0301 receipts.\n\nPaid.")

    assert result.text == "Caf\u00e9 receipts.\n\nPaid."
    assert spans(result) == ["Caf\u00e9 receipts.", "Paid."]


@pytest.mark.parametrize("media_type", ["text/markdown", "text/csv"])
def test_any_text_media_type_may_be_segmented(
    media_type: str,
) -> None:
    assert segmented(media_type=media_type).media_type == media_type


@pytest.mark.parametrize("media_type", ["application/json", "application/pdf", "image/png"])
def test_only_text_is_segmented(
    media_type: str,
) -> None:
    with pytest.raises(ValueError) as raised:
        segmented(media_type=media_type)

    assert str(raised.value) == f"segment_text segments text/* content; got {media_type!r}."


def test_the_same_text_always_segments_to_the_same_extraction() -> None:
    assert segmented().digest() == segmented().digest()


def test_a_segmented_text_can_be_stored_and_cited() -> None:
    store = InMemoryContentStore()
    result = segmented()

    loaded = SegmentedText.load(store, result.store(store))

    assert loaded is not None

    check = verify_citation(loaded, segment_id="s2", quote="received on December 14")

    assert check.status is CitationStatus.VERIFIED
    assert check.anchor is not None
    assert check.anchor.extraction == result.extraction()


def test_the_readme_example_verifies_its_citation() -> None:
    readme = (Path(__file__).parents[2] / "src" / "azathoth" / "citations" / "README.md").read_text(
        encoding="utf-8"
    )

    (example,) = [
        block
        for block in re.findall(r"```python\n(.*?)\n```", readme, re.DOTALL)
        if "segment_text(" in block
    ]

    namespace: dict[str, object] = {}
    exec(example, namespace)

    check = namespace["check"]

    assert isinstance(check, CitationCheck)
    assert check.status is CitationStatus.VERIFIED
