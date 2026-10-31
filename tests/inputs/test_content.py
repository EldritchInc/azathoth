"""Tests for decoding input content by media type (ADR 0096)."""

import pytest

from azathoth.inputs import (
    InputContentError,
    decode_content,
    infer_media_type,
)


def test_json_content_is_parsed() -> None:
    assert decode_content(b'{"chapters": [1, 2]}', "application/json") == {"chapters": [1, 2]}


def test_json_content_may_be_any_json_value() -> None:
    assert decode_content(b'"text"', "application/json") == "text"
    assert decode_content(b"null", "application/json") is None


def test_text_content_is_decoded_as_a_string() -> None:
    assert decode_content("Café — the end.\n".encode(), "text/markdown") == "Café — the end.\n"


def test_text_content_keeps_json_looking_text_as_text() -> None:
    assert decode_content(b'{"a": 1}', "text/plain") == '{"a": 1}'


def test_a_utf8_byte_order_mark_is_dropped() -> None:
    assert decode_content(b'\xef\xbb\xbf{"a": 1}', "application/json") == {"a": 1}
    assert decode_content(b"\xef\xbb\xbfhello", "text/plain") == "hello"


def test_empty_text_content_is_an_empty_string() -> None:
    assert decode_content(b"", "text/plain") == ""


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(InputContentError, match="Content is not valid UTF-8"):
        decode_content(b"\xff\xfe", "text/plain")


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"{not json", id="malformed"),
        pytest.param(b"", id="empty"),
    ],
)
def test_invalid_json_is_rejected(
    content: bytes,
) -> None:
    with pytest.raises(InputContentError, match="Content is not valid JSON"):
        decode_content(content, "application/json")


@pytest.mark.parametrize(
    "constant",
    ["NaN", "Infinity", "-Infinity"],
)
def test_json_content_rejects_non_finite_numbers(
    constant: str,
) -> None:
    with pytest.raises(InputContentError, match=f"Content is not valid JSON: {constant}"):
        decode_content(f'{{"a": {constant}}}'.encode(), "application/json")


def test_unsupported_media_types_are_rejected() -> None:
    with pytest.raises(InputContentError, match="Media type 'image/png' is not supported"):
        decode_content(b"\x89PNG", "image/png")


def test_input_content_error_is_a_value_error() -> None:
    assert issubclass(InputContentError, ValueError)


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("request.json", "application/json"),
        ("notes.txt", "text/plain"),
        ("chapter.md", "text/markdown"),
        ("chapter.markdown", "text/markdown"),
        ("rows.csv", "text/csv"),
        ("CHAPTER.MD", "text/markdown"),
        ("archive.tar.json", "application/json"),
    ],
)
def test_media_types_are_inferred_from_known_extensions(
    name: str,
    media_type: str,
) -> None:
    assert infer_media_type(name) == media_type


@pytest.mark.parametrize(
    "name",
    ["scan.pdf", "photo.png", "README", "notes.", ".json"],
)
def test_unknown_extensions_infer_no_media_type(
    name: str,
) -> None:
    assert infer_media_type(name) is None
