"""Tests for binary media types and the content handles workflows receive (ADR 0112)."""

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.inputs import (
    BINARY_MEDIA_TYPES,
    CONTENT_REF_KEY,
    JPEG_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    PNG_MEDIA_TYPE,
    WEBP_MEDIA_TYPE,
    ContentRef,
    InputContentError,
    check_binary_signature,
    content_bytes_digest,
    content_ref_from_value,
    decode_content,
    infer_media_type,
    is_binary_media_type,
    is_supported_media_type,
    is_text_media_type,
    validate_media_type,
)

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "

DIGEST = content_bytes_digest(PDF)


def test_the_binary_media_types_are_pdf_and_three_image_formats() -> None:
    assert (
        frozenset({"application/pdf", "image/png", "image/jpeg", "image/webp"})
        == BINARY_MEDIA_TYPES
    )
    assert (PDF_MEDIA_TYPE, PNG_MEDIA_TYPE, JPEG_MEDIA_TYPE, WEBP_MEDIA_TYPE) == (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
    )


@pytest.mark.parametrize("media_type", sorted(BINARY_MEDIA_TYPES))
def test_binary_media_types_are_supported_and_not_text(
    media_type: str,
) -> None:
    assert is_supported_media_type(media_type)
    assert is_binary_media_type(media_type)
    assert not is_text_media_type(media_type)
    assert validate_media_type(media_type) == media_type


@pytest.mark.parametrize(
    "media_type",
    ["application/json", "text/plain", "image/gif", "application/octet-stream", "image/svg+xml"],
)
def test_other_media_types_are_not_binary(
    media_type: str,
) -> None:
    assert not is_binary_media_type(media_type)


@pytest.mark.parametrize(
    "media_type",
    ["image/gif", "image/svg+xml", "application/octet-stream", "application/zip"],
)
def test_other_binary_formats_are_refused_naming_what_is_accepted(
    media_type: str,
) -> None:
    assert not is_supported_media_type(media_type)

    with pytest.raises(ValueError) as raised:
        validate_media_type(media_type)

    assert str(raised.value) == (
        f"Media type {media_type!r} is not supported; Azathoth accepts application/json, "
        "text/* media types, application/pdf, image/jpeg, image/png and image/webp."
    )


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("scan.pdf", "application/pdf"),
        ("SCAN.PDF", "application/pdf"),
        ("photo.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("photo.JPEG", "image/jpeg"),
        ("sticker.webp", "image/webp"),
    ],
)
def test_binary_media_types_are_inferred_from_their_extensions(
    name: str,
    media_type: str,
) -> None:
    assert infer_media_type(name) == media_type


@pytest.mark.parametrize(
    ("content", "media_type"),
    [
        pytest.param(PDF, "application/pdf", id="pdf"),
        pytest.param(b"\n" * 1019 + b"%PDF-", "application/pdf", id="pdf-header-at-1019"),
        pytest.param(PNG, "image/png", id="png"),
        pytest.param(JPEG, "image/jpeg", id="jpeg"),
        pytest.param(WEBP, "image/webp", id="webp"),
    ],
)
def test_content_matching_its_signature_is_accepted(
    content: bytes,
    media_type: str,
) -> None:
    check_binary_signature(content, media_type)


@pytest.mark.parametrize(
    ("content", "media_type", "message"),
    [
        pytest.param(
            PNG,
            "application/pdf",
            "Content is not application/pdf: no PDF header in its first 1024 bytes.",
            id="png-as-pdf",
        ),
        pytest.param(
            b"\n" * 1020 + b"%PDF-",
            "application/pdf",
            "Content is not application/pdf: no PDF header in its first 1024 bytes.",
            id="pdf-header-past-1024",
        ),
        pytest.param(
            b"%PDF",
            "application/pdf",
            "Content is not application/pdf: no PDF header in its first 1024 bytes.",
            id="pdf-header-cut-short",
        ),
        pytest.param(
            JPEG,
            "image/png",
            "Content is not image/png: it does not start with the PNG signature.",
            id="jpeg-as-png",
        ),
        pytest.param(
            b"",
            "image/png",
            "Content is not image/png: it does not start with the PNG signature.",
            id="empty-png",
        ),
        pytest.param(
            b"\xff\xd8",
            "image/jpeg",
            "Content is not image/jpeg: it does not start with a JPEG start-of-image marker.",
            id="jpeg-cut-short",
        ),
        pytest.param(
            b"RIFF\x24\x00\x00\x00WAVEfmt ",
            "image/webp",
            "Content is not image/webp: it is not a RIFF container holding WEBP.",
            id="wav-as-webp",
        ),
        pytest.param(
            b"RIFX\x24\x00\x00\x00WEBPVP8 ",
            "image/webp",
            "Content is not image/webp: it is not a RIFF container holding WEBP.",
            id="big-endian-riff",
        ),
    ],
)
def test_content_not_matching_its_signature_is_refused(
    content: bytes,
    media_type: str,
    message: str,
) -> None:
    with pytest.raises(InputContentError) as raised:
        check_binary_signature(content, media_type)

    assert str(raised.value) == message


def test_only_binary_media_types_have_signatures() -> None:
    with pytest.raises(ValueError) as raised:
        check_binary_signature(b"{}", "application/json")

    assert str(raised.value) == "Media type 'application/json' is not a binary media type."


@pytest.mark.parametrize("media_type", sorted(BINARY_MEDIA_TYPES))
def test_binary_content_is_never_decoded_into_a_value(
    media_type: str,
) -> None:
    with pytest.raises(InputContentError) as raised:
        decode_content(PDF, media_type)

    assert str(raised.value) == (
        f"Media type {media_type} is binary: its content is stored and given to a "
        "workflow as a content handle, not decoded into a value."
    )


def test_a_content_handle_holds_digest_media_type_and_size() -> None:
    ref = ContentRef(digest=DIGEST, media_type="application/pdf", size_bytes=len(PDF))

    assert CONTENT_REF_KEY == "content"
    assert ref.to_value() == {
        "content": {
            "digest": DIGEST,
            "media_type": "application/pdf",
            "size_bytes": len(PDF),
        }
    }


def test_a_content_handle_is_frozen() -> None:
    ref = ContentRef(digest=DIGEST, media_type="image/png", size_bytes=3)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        ref.__setattr__("size_bytes", 4)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"digest": "ABC", "media_type": "image/png", "size_bytes": 1},
            "String should match pattern",
            id="malformed-digest",
        ),
        pytest.param(
            {"digest": DIGEST, "media_type": "text/plain", "size_bytes": 1},
            "A content handle names binary content; 'text/plain' is not a binary media type.",
            id="text-media-type",
        ),
        pytest.param(
            {"digest": DIGEST, "media_type": "image/png", "size_bytes": -1},
            "greater than or equal to 0",
            id="negative-size",
        ),
        pytest.param(
            {"digest": DIGEST, "media_type": "image/png", "size_bytes": 1, "uri": "s3://b/k"},
            "Extra inputs are not permitted",
            id="extra-field",
        ),
    ],
)
def test_a_content_handle_validates_its_fields(
    fields: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        ContentRef.model_validate(fields)


def test_a_handles_value_parses_back_into_the_handle() -> None:
    ref = ContentRef(digest=DIGEST, media_type="image/webp", size_bytes=12)

    assert content_ref_from_value(ref.to_value()) == ref


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="null"),
        pytest.param("content", id="string"),
        pytest.param([{"content": {}}], id="list"),
        pytest.param({"content": {"digest": DIGEST}}, id="incomplete"),
        pytest.param(
            {
                "content": {"digest": DIGEST, "media_type": "image/png", "size_bytes": 1},
                "note": "extra",
            },
            id="extra-key-beside-content",
        ),
        pytest.param(
            {"content": {"digest": DIGEST, "media_type": "text/plain", "size_bytes": 1}},
            id="text-media-type",
        ),
        pytest.param(
            {"digest": DIGEST, "media_type": "image/png", "size_bytes": 1},
            id="flat",
        ),
    ],
)
def test_other_values_are_not_content_handles(
    value: JsonValue,
) -> None:
    assert content_ref_from_value(value) is None
