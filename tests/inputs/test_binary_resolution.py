"""Tests for resolving binary references into content handles (ADR 0112)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.inputs import (
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    ReferenceInput,
    ResolvedInput,
    content_bytes_digest,
    file_uri,
    resolve_input,
)

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def file_policy(
    max_bytes: int = 1024,
) -> InputPolicy:
    """Return a policy accepting local files within a small cap."""

    return InputPolicy(
        resolvers={"file": FileInputResolver()},
        max_bytes=max_bytes,
    )


def write(
    path: Path,
    content: bytes,
) -> Path:
    """Write content to one file and return its path."""

    path.write_bytes(content)

    return path


def test_a_binary_reference_resolves_to_a_content_handle(
    tmp_path: Path,
) -> None:
    uri = file_uri(write(tmp_path / "scan.pdf", PDF))
    store = InMemoryContentStore()

    resolved = resolve_input(
        ReferenceInput(uri=uri, media_type="application/pdf"),
        policy=file_policy(),
        store=store,
    )

    digest = content_bytes_digest(PDF)

    assert resolved == ResolvedInput(
        value={
            "content": {
                "digest": digest,
                "media_type": "application/pdf",
                "size_bytes": len(PDF),
            }
        },
        media_type="application/pdf",
        provenance=InputProvenance(
            uri=uri,
            media_type="application/pdf",
            size_bytes=len(PDF),
            digest=digest,
        ),
    )
    assert store.get(digest) == PDF


def test_a_binary_reference_not_matching_its_type_is_refused_and_not_stored(
    tmp_path: Path,
) -> None:
    uri = file_uri(write(tmp_path / "scan.pdf", PNG))
    store = InMemoryContentStore()

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri=uri, media_type="application/pdf"),
            policy=file_policy(),
            store=store,
        )

    assert str(raised.value) == (
        f"Input {uri}: Content is not application/pdf: no PDF header in its first 1024 bytes."
    )
    assert not store.contains(content_bytes_digest(PNG))


def test_a_binary_reference_beyond_the_cap_is_refused(
    tmp_path: Path,
) -> None:
    uri = file_uri(write(tmp_path / "photo.png", PNG + b"\x00" * 64))

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri=uri, media_type="image/png"),
            policy=file_policy(max_bytes=len(PNG)),
            store=InMemoryContentStore(),
        )

    assert str(raised.value) == f"Input {uri} is larger than the limit of {len(PNG)} bytes."


def test_a_text_reference_still_resolves_to_its_string(
    tmp_path: Path,
) -> None:
    uri = file_uri(write(tmp_path / "notes.txt", b"plain words"))

    resolved = resolve_input(
        ReferenceInput(uri=uri, media_type="text/plain"),
        policy=file_policy(),
        store=InMemoryContentStore(),
    )

    assert resolved.value == "plain words"


@pytest.mark.parametrize("media_type", ["application/pdf", "image/png"])
def test_an_inline_binary_input_is_not_accepted_yet(
    media_type: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        InlineInput(value="JVBERi0=", media_type=media_type)

    assert f"An inline {media_type} input is not accepted yet; give it by reference." in str(
        raised.value
    )
