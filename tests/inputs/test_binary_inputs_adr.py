"""Tests that ADR 0112 states binary inputs as they really behave."""

from pathlib import Path

import pytest

from azathoth.inputs import (
    BINARY_MEDIA_TYPES,
    DEFAULT_MAX_INPUT_BYTES,
    MEDIA_TYPES_BY_EXTENSION,
    InputContentError,
    check_binary_signature,
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
