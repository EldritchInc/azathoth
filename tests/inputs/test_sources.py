"""Tests for value-or-reference workflow input sources (ADR 0096)."""

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from azathoth.inputs import (
    JSON_MEDIA_TYPE,
    InlineInput,
    InputSourceError,
    ReferenceInput,
    WorkflowInputSource,
    decode_input_source,
    is_supported_media_type,
    validate_media_type,
)

CHAPTER_URI = "file:///Users/you/chapter.md"


class Envelope(BaseModel):
    """A model that embeds an input source, as the job envelope will."""

    input: WorkflowInputSource


def test_inline_input_defaults_to_json() -> None:
    source = InlineInput(value={"text": "the old ones wait"})

    assert source.media_type == JSON_MEDIA_TYPE == "application/json"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"a": [1, 2]}, id="object"),
        pytest.param([1, "two"], id="list"),
        pytest.param("text", id="string"),
        pytest.param(3.5, id="number"),
        pytest.param(True, id="boolean"),
        pytest.param(None, id="null"),
    ],
)
def test_inline_json_input_holds_any_json_value(
    value: JsonValue,
) -> None:
    assert InlineInput(value=value).value == value


def test_inline_text_input_holds_a_string() -> None:
    source = InlineInput(value="Chapter one.", media_type="text/markdown")

    assert source.value == "Chapter one."


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"text": "x"}, id="object"),
        pytest.param(3, id="number"),
        pytest.param(None, id="null"),
    ],
)
def test_inline_text_input_rejects_a_value_that_is_not_a_string(
    value: JsonValue,
) -> None:
    with pytest.raises(ValidationError, match="An inline text/plain input must hold a string."):
        InlineInput(value=value, media_type="text/plain")


def test_reference_input_requires_a_media_type() -> None:
    with pytest.raises(ValidationError):
        ReferenceInput.model_validate({"uri": CHAPTER_URI})


def test_reference_input_reports_its_scheme_in_lowercase() -> None:
    source = ReferenceInput(uri="FILE:///Users/you/chapter.md", media_type="text/markdown")

    assert source.scheme == "file"


@pytest.mark.parametrize(
    "uri",
    [
        pytest.param("chapter.md", id="relative-path"),
        pytest.param("/Users/you/chapter.md", id="absolute-path"),
        pytest.param("C:\\Users\\you\\chapter.md", id="windows-path"),
        pytest.param("", id="empty"),
    ],
)
def test_reference_input_requires_a_uri_with_a_scheme(
    uri: str,
) -> None:
    with pytest.raises(ValidationError, match="must be a URI with a scheme"):
        ReferenceInput(uri=uri, media_type="text/plain")


@pytest.mark.parametrize(
    "media_type",
    [
        "application/json",
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/vnd.a+b",
    ],
)
def test_json_and_text_media_types_are_supported(
    media_type: str,
) -> None:
    assert is_supported_media_type(media_type)
    assert validate_media_type(media_type) == media_type


@pytest.mark.parametrize(
    "media_type",
    [
        "image/png",
        "application/pdf",
        "application/octet-stream",
    ],
)
def test_binary_media_types_are_not_supported_yet(
    media_type: str,
) -> None:
    assert not is_supported_media_type(media_type)

    with pytest.raises(ValueError, match=f"Media type '{media_type}' is not supported"):
        validate_media_type(media_type)


@pytest.mark.parametrize(
    "media_type",
    [
        pytest.param("Text/Plain", id="uppercase"),
        pytest.param("text/plain; charset=utf-8", id="parameters"),
        pytest.param("text", id="no-subtype"),
        pytest.param("text/", id="empty-subtype"),
        pytest.param("/plain", id="empty-type"),
        pytest.param("", id="empty"),
    ],
)
def test_malformed_media_types_are_rejected(
    media_type: str,
) -> None:
    with pytest.raises(ValueError, match="must be a lowercase type/subtype with no parameters"):
        validate_media_type(media_type)


def test_sources_reject_unsupported_media_types() -> None:
    with pytest.raises(ValidationError, match="is not supported"):
        InlineInput(value="x", media_type="image/png")

    with pytest.raises(ValidationError, match="is not supported"):
        ReferenceInput(uri=CHAPTER_URI, media_type="image/png")


def test_decode_input_source_reads_an_inline_value() -> None:
    assert decode_input_source({"value": [1, 2]}) == InlineInput(value=[1, 2])


def test_decode_input_source_reads_an_inline_null() -> None:
    assert decode_input_source({"value": None}) == InlineInput(value=None)


def test_decode_input_source_reads_a_reference() -> None:
    assert decode_input_source({"uri": CHAPTER_URI, "media_type": "text/markdown"}) == (
        ReferenceInput(uri=CHAPTER_URI, media_type="text/markdown")
    )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(
            {"value": 1, "uri": CHAPTER_URI, "media_type": "text/plain"},
            "An input source holds exactly one of 'value' and 'uri'.",
            id="both",
        ),
        pytest.param(
            {"media_type": "text/plain"},
            "An input source holds exactly one of 'value' and 'uri'.",
            id="neither",
        ),
        pytest.param(
            {"value": 1, "unit": "seconds"},
            "An input source holds only 'value' or 'uri', and 'media_type'; got 'unit'.",
            id="extra-key",
        ),
        pytest.param(
            [1, 2],
            "An input source must be a JSON object.",
            id="not-an-object",
        ),
        pytest.param(
            {"uri": CHAPTER_URI},
            "Input reference",
            id="reference-without-media-type",
        ),
        pytest.param(
            {"value": 3, "media_type": "text/plain"},
            "An inline text/plain input must hold a string.",
            id="text-not-string",
        ),
    ],
)
def test_decode_input_source_rejects_malformed_sources(
    data: JsonValue,
    message: str,
) -> None:
    with pytest.raises(InputSourceError, match=message):
        decode_input_source(data)


def test_input_source_error_is_a_value_error() -> None:
    assert issubclass(InputSourceError, ValueError)


def test_an_embedded_source_parses_by_its_key() -> None:
    inline = Envelope.model_validate({"input": {"value": "x", "media_type": "text/plain"}})
    reference = Envelope.model_validate(
        {"input": {"uri": CHAPTER_URI, "media_type": "text/markdown"}},
    )

    assert inline.input == InlineInput(value="x", media_type="text/plain")
    assert reference.input == ReferenceInput(uri=CHAPTER_URI, media_type="text/markdown")


def test_an_embedded_source_rejects_both_keys() -> None:
    with pytest.raises(ValidationError, match="exactly one of 'value' and 'uri'"):
        Envelope.model_validate(
            {"input": {"value": 1, "uri": CHAPTER_URI, "media_type": "text/plain"}},
        )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(InlineInput(value={"a": 1}), id="inline"),
        pytest.param(InlineInput(value="x", media_type="text/plain"), id="inline-text"),
        pytest.param(ReferenceInput(uri=CHAPTER_URI, media_type="text/markdown"), id="reference"),
    ],
)
def test_sources_round_trip_through_json(
    source: InlineInput | ReferenceInput,
) -> None:
    envelope = Envelope(input=source)

    assert Envelope.model_validate_json(envelope.model_dump_json()) == envelope


def test_sources_serialize_as_their_written_shape() -> None:
    assert InlineInput(value=[1]).model_dump(mode="json") == {
        "value": [1],
        "media_type": "application/json",
    }
    assert ReferenceInput(uri=CHAPTER_URI, media_type="text/markdown").model_dump(
        mode="json",
    ) == {"uri": CHAPTER_URI, "media_type": "text/markdown"}
