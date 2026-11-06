"""Tests that ADR 0112 states binary inputs as they really behave."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.inputs import (
    BINARY_MEDIA_TYPES,
    DEFAULT_MAX_INPUT_BYTES,
    MAX_ORIGIN_URI_LENGTH,
    MEDIA_TYPES_BY_EXTENSION,
    ORIGIN_ON_REFERENCE_MESSAGE,
    InlineInput,
    InMemoryContentStore,
    InputContentError,
    InputOrigin,
    InputPolicy,
    InputResolutionError,
    check_binary_signature,
    resolve_input,
    validate_media_type,
)

ADR = Path(__file__).parents[2] / "docs" / "adrs" / "0112-accept-binary-inputs.md"


def text() -> str:
    """Return the ADR."""

    return ADR.read_text(encoding="utf-8")


def prose() -> str:
    """Return the ADR with its lines joined, as it reads."""

    return " ".join(text().split())


def assert_quoted(
    message: str,
) -> None:
    """Check the ADR quotes one message as a whole `text` block."""

    assert f"```text\n{message}\n```" in text(), message


def test_the_adr_names_every_binary_media_type() -> None:
    for media_type in BINARY_MEDIA_TYPES:
        assert f"`{media_type}`" in text(), media_type


def test_the_adr_names_every_inferred_extension() -> None:
    for extension in MEDIA_TYPES_BY_EXTENSION:
        assert f"`{extension}`" in text(), extension


def test_the_adr_quotes_the_refusal_of_another_media_type() -> None:
    with pytest.raises(ValueError) as raised:
        validate_media_type("image/gif")

    assert_quoted(str(raised.value))


@pytest.mark.parametrize("media_type", sorted(BINARY_MEDIA_TYPES))
def test_the_adr_quotes_each_signature_refusal(
    media_type: str,
) -> None:
    with pytest.raises(InputContentError) as raised:
        check_binary_signature(b"", media_type)

    assert_quoted(str(raised.value))


def test_the_adr_says_where_a_pdf_header_may_be() -> None:
    check_binary_signature(b" " * 1019 + b"%PDF-", "application/pdf")

    with pytest.raises(InputContentError):
        check_binary_signature(b" " * 1020 + b"%PDF-", "application/pdf")

    assert "`%PDF-` header within its first 1024 bytes" in prose()


def test_the_adr_states_the_clis_default_cap() -> None:
    assert DEFAULT_MAX_INPUT_BYTES == 10 * 1024 * 1024
    assert "the CLI's default of 10 MiB" in prose()


def validation_message(
    error: ValidationError,
) -> str:
    """Return one validation error's single message, without pydantic's prefix."""

    (detail,) = error.errors(include_url=False)

    return str(detail["msg"]).removeprefix("Value error, ")


def test_the_adr_quotes_the_refusal_of_a_non_string_inline_binary_value() -> None:
    with pytest.raises(ValidationError) as raised:
        InlineInput(value=3, media_type="application/pdf")

    assert_quoted(validation_message(raised.value))


def test_the_adr_quotes_the_refusal_of_malformed_base64() -> None:
    with pytest.raises(ValidationError) as raised:
        InlineInput(value="JVBERi0xLjc", media_type="application/pdf")

    assert_quoted(validation_message(raised.value))


def test_the_adr_quotes_the_refusal_of_inline_content_beyond_the_cap() -> None:
    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            InlineInput(value="AAAA" * 4, media_type="application/pdf"),
            policy=InputPolicy(max_bytes=10),
            store=InMemoryContentStore(),
        )

    assert_quoted(str(raised.value).replace("10 bytes", "10485760 bytes"))


def test_the_adr_quotes_the_refusal_of_an_origin_on_a_reference() -> None:
    assert_quoted(ORIGIN_ON_REFERENCE_MESSAGE)


def test_the_adr_quotes_the_refusal_of_a_version_off_s3() -> None:
    with pytest.raises(ValidationError) as raised:
        InputOrigin(uri="https://docs.example.com/claims/0412", etag="9b2c")

    assert_quoted(validation_message(raised.value))


def test_the_adr_states_the_longest_origin_uri() -> None:
    assert MAX_ORIGIN_URI_LENGTH == 2048
    assert "at most 2048 characters" in prose()


def test_the_adr_states_how_the_encoded_length_is_bounded() -> None:
    assert "four characters for every three bytes" in prose()


def test_the_adr_says_an_s3_reference_records_the_version_it_read() -> None:
    assert "the `VersionId` and `ETag` of the response that held the bytes" in prose()
    assert "read once more, plainly, for its version" in prose()
