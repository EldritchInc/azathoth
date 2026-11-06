"""Tests for inline binary content and the origin an inline input may name (ADR 0112)."""

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from azathoth.inputs import (
    ORIGIN_ON_REFERENCE_MESSAGE,
    InlineInput,
    InputOrigin,
    InputSourceError,
    WorkflowInputSource,
    decode_input_source,
)

PDF_BASE64 = "JVBERi0xLjcK"

S3_URI = "s3://claims-intake/2026/11/claim-0412.pdf"


class Envelope(BaseModel):
    """A model that embeds an input source, as the job envelope does."""

    input: WorkflowInputSource


def test_an_origin_holds_a_uri_and_optionally_an_s3_version() -> None:
    origin = InputOrigin(uri=S3_URI, version_id="3HL4kqtJlcpXroDTDmJ", etag="9b2cf535f27731c9")

    assert origin.model_dump(mode="json") == {
        "uri": S3_URI,
        "version_id": "3HL4kqtJlcpXroDTDmJ",
        "etag": "9b2cf535f27731c9",
    }


def test_an_origin_leaves_out_a_version_and_etag_it_does_not_have() -> None:
    origin = InputOrigin(uri="https://docs.example.com/claims/0412")

    assert origin.model_dump(mode="json") == {"uri": "https://docs.example.com/claims/0412"}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"uri": "claim-0412.pdf"},
            "An origin 'claim-0412.pdf' must be a URI with a scheme, such as s3://bucket/key.",
            id="no-scheme",
        ),
        pytest.param(
            {"uri": "C:/claims/claim-0412.pdf"},
            "An origin 'C:/claims/claim-0412.pdf' must be a URI with a scheme, "
            "such as s3://bucket/key.",
            id="drive-letter",
        ),
        pytest.param(
            {"uri": f"{S3_URI}#page=3"},
            f"An origin '{S3_URI}#page=3' names a whole object, with no fragment.",
            id="fragment",
        ),
        pytest.param(
            {"uri": "https://docs.example.com/" + "a" * 2025},
            "An origin URI holds at most 2048 characters; got 2050.",
            id="too-long",
        ),
        pytest.param(
            {"uri": "https://docs.example.com/claims/0412", "version_id": "3HL4"},
            "An origin's version_id and etag name an S3 object version; "
            "'https://docs.example.com/claims/0412' is not an s3:// URI.",
            id="version-off-s3",
        ),
        pytest.param(
            {"uri": "file:///Users/you/claim.pdf", "etag": "9b2c"},
            "An origin's version_id and etag name an S3 object version; "
            "'file:///Users/you/claim.pdf' is not an s3:// URI.",
            id="etag-off-s3",
        ),
        pytest.param(
            {"uri": S3_URI, "version_id": ""},
            "String should have at least 1 character",
            id="empty-version",
        ),
        pytest.param(
            {"uri": S3_URI, "bucket": "claims-intake"},
            "Extra inputs are not permitted",
            id="extra-field",
        ),
    ],
)
def test_an_origin_is_validated(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        InputOrigin.model_validate(fields)

    assert message in str(raised.value)


def test_an_origin_of_2048_characters_is_accepted() -> None:
    uri = "https://docs.example.com/" + "a" * 2023

    assert len(uri) == 2048
    assert InputOrigin(uri=uri).uri == uri


def test_an_s3_origins_scheme_is_matched_in_any_case() -> None:
    assert InputOrigin(uri="S3://claims-intake/k", etag="9b2c").etag == "9b2c"


def test_an_inline_binary_input_holds_base64() -> None:
    source = InlineInput(value=PDF_BASE64, media_type="application/pdf")

    assert (source.value, source.media_type, source.origin) == (
        PDF_BASE64,
        "application/pdf",
        None,
    )


def test_empty_base64_is_well_formed() -> None:
    assert InlineInput(value="", media_type="image/png").value == ""


@pytest.mark.parametrize(
    "value",
    [{"base64": PDF_BASE64}, 3, None, [PDF_BASE64]],
)
def test_an_inline_binary_input_must_hold_a_string(
    value: JsonValue,
) -> None:
    with pytest.raises(ValidationError) as raised:
        InlineInput(value=value, media_type="application/pdf")

    assert "An inline application/pdf input must hold its content as a base64 string." in str(
        raised.value
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("JVBERi0xLjcK\n", id="trailing-newline"),
        pytest.param("JVBE Ri0xLjcK", id="space"),
        pytest.param("JVBERi0xLjc", id="unpadded"),
        pytest.param("JVBERi0xLjcK==", id="padding-after-a-full-block"),
        pytest.param("JVBE=i0xLjcK", id="padding-inside"),
        pytest.param("JVBERi0x-_cK", id="url-safe-alphabet"),
        pytest.param("data:application/pdf;base64,JVBERi0xLjcK", id="data-url"),
        pytest.param("A===", id="three-pads"),
    ],
)
def test_an_inline_binary_input_must_be_standard_padded_base64(
    value: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        InlineInput(value=value, media_type="image/png")

    assert (
        "An inline image/png input must hold standard base64, padded, with no whitespace."
        in str(raised.value)
    )


@pytest.mark.parametrize(
    ("value", "media_type"),
    [
        pytest.param(PDF_BASE64, "application/pdf", id="binary"),
        pytest.param("Mara climbed the stairs.", "text/plain", id="text"),
        pytest.param({"claim": "0412"}, "application/json", id="json"),
    ],
)
def test_any_inline_input_may_name_its_origin(
    value: JsonValue,
    media_type: str,
) -> None:
    source = decode_input_source(
        {"value": value, "media_type": media_type, "origin": {"uri": S3_URI, "etag": "9b2c"}}
    )

    assert source == InlineInput(
        value=value,
        media_type=media_type,
        origin=InputOrigin(uri=S3_URI, etag="9b2c"),
    )


def test_a_reference_may_not_name_an_origin() -> None:
    data: JsonValue = {
        "uri": S3_URI,
        "media_type": "application/pdf",
        "origin": {"uri": S3_URI},
    }

    assert ORIGIN_ON_REFERENCE_MESSAGE == (
        "A reference is its own origin; 'origin' is given only with an inline 'value'."
    )

    with pytest.raises(InputSourceError) as raised:
        decode_input_source(data)

    assert str(raised.value) == ORIGIN_ON_REFERENCE_MESSAGE

    with pytest.raises(ValidationError) as embedded:
        Envelope.model_validate({"input": data})

    assert ORIGIN_ON_REFERENCE_MESSAGE in str(embedded.value)


def test_an_embedded_inline_source_reads_its_origin() -> None:
    envelope = Envelope.model_validate(
        {
            "input": {
                "value": PDF_BASE64,
                "media_type": "application/pdf",
                "origin": {"uri": S3_URI},
            }
        }
    )

    assert envelope.input == InlineInput(
        value=PDF_BASE64,
        media_type="application/pdf",
        origin=InputOrigin(uri=S3_URI),
    )


def test_an_inline_input_without_an_origin_dumps_as_it_always_has() -> None:
    assert InlineInput(value={"a": 1}).model_dump(mode="json") == {
        "value": {"a": 1},
        "media_type": "application/json",
    }


def test_an_inline_input_with_an_origin_dumps_it() -> None:
    source = InlineInput(value="x", media_type="text/plain", origin=InputOrigin(uri=S3_URI))

    assert source.model_dump(mode="json") == {
        "value": "x",
        "media_type": "text/plain",
        "origin": {"uri": S3_URI},
    }


def test_an_invalid_origin_is_reported_through_decode_input_source() -> None:
    with pytest.raises(InputSourceError) as raised:
        decode_input_source({"value": 1, "origin": {"uri": "claim.pdf"}})

    assert str(raised.value) == (
        "An origin 'claim.pdf' must be a URI with a scheme, such as s3://bucket/key."
    )
