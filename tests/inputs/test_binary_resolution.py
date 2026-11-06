"""Tests for resolving binary inputs into content handles (ADR 0112)."""

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.inputs import (
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputOrigin,
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

S3_URI = "s3://claims-intake/2026/11/claim-0412.pdf"


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


def test_an_inline_binary_input_resolves_to_a_content_handle() -> None:
    store = InMemoryContentStore()

    resolved = resolve_input(
        InlineInput(value=base64.b64encode(PDF).decode("ascii"), media_type="application/pdf"),
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
            inline=True,
            media_type="application/pdf",
            size_bytes=len(PDF),
            digest=digest,
        ),
    )
    assert store.get(digest) == PDF


def test_an_inline_binary_input_records_the_origin_it_names() -> None:
    origin = InputOrigin(uri=S3_URI, version_id="3HL4kqtJlcpXroDTDmJ", etag="9b2cf535")

    resolved = resolve_input(
        InlineInput(
            value=base64.b64encode(PNG).decode("ascii"),
            media_type="image/png",
            origin=origin,
        ),
        policy=file_policy(),
        store=InMemoryContentStore(),
    )

    assert resolved.provenance == InputProvenance(
        inline=True,
        origin=origin,
        media_type="image/png",
        size_bytes=len(PNG),
        digest=content_bytes_digest(PNG),
    )


def test_an_inline_binary_input_needs_no_accepted_scheme() -> None:
    resolved = resolve_input(
        InlineInput(value=base64.b64encode(PNG).decode("ascii"), media_type="image/png"),
        policy=InputPolicy(),
        store=InMemoryContentStore(),
    )

    assert resolved.media_type == "image/png"


def test_an_inline_binary_input_not_matching_its_type_is_refused_and_not_stored() -> None:
    store = InMemoryContentStore()

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            InlineInput(value=base64.b64encode(PNG).decode("ascii"), media_type="image/webp"),
            policy=file_policy(),
            store=store,
        )

    assert str(raised.value) == (
        "Inline input: Content is not image/webp: it is not a RIFF container holding WEBP."
    )
    assert not store.contains(content_bytes_digest(PNG))


def test_inline_base64_longer_than_the_cap_allows_is_refused_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryContentStore()

    def refuse_to_decode(
        encoded: str,
        *,
        validate: bool,
    ) -> bytes:
        """Fail the test if anything is decoded."""

        raise AssertionError(f"decoded {len(encoded)} characters")

    monkeypatch.setattr(base64, "b64decode", refuse_to_decode)

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            InlineInput(value="AAAA" * 3, media_type="image/png"),
            policy=file_policy(max_bytes=6),
            store=store,
        )

    assert str(raised.value) == "Inline input is larger than the limit of 6 bytes."


@pytest.mark.parametrize(
    "size",
    [
        pytest.param(8, id="cap-not-a-multiple-of-three"),
        pytest.param(9, id="cap-a-multiple-of-three"),
    ],
)
def test_inline_base64_of_exactly_the_cap_is_accepted(
    size: int,
) -> None:
    content = (PNG[:8] + b"\x00")[:size]

    resolved = resolve_input(
        InlineInput(value=base64.b64encode(content).decode("ascii"), media_type="image/png"),
        policy=file_policy(max_bytes=len(content)),
        store=InMemoryContentStore(),
    )

    assert resolved.provenance is not None
    assert resolved.provenance.size_bytes == len(content)


def test_inline_content_decoding_past_the_cap_is_refused() -> None:
    #
    # Nine bytes encode as twelve characters, which a cap of eight still
    # allows (eight bytes may need twelve), so only the decoded size is over.
    #
    content = PNG[:8] + b"\x00"

    assert len(base64.b64encode(content)) == 12

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            InlineInput(value=base64.b64encode(content).decode("ascii"), media_type="image/png"),
            policy=file_policy(max_bytes=len(content) - 1),
            store=InMemoryContentStore(),
        )

    limit = len(content) - 1

    assert str(raised.value) == f"Inline input is larger than the limit of {limit} bytes."


def test_inline_text_with_an_origin_records_its_utf8_bytes() -> None:
    store = InMemoryContentStore()
    text = "Mara climbed the stairs — again.\n"

    resolved = resolve_input(
        InlineInput(value=text, media_type="text/plain", origin=InputOrigin(uri=S3_URI)),
        policy=file_policy(),
        store=store,
    )

    content = text.encode("utf-8")

    assert resolved.value == text
    assert resolved.provenance == InputProvenance(
        inline=True,
        origin=InputOrigin(uri=S3_URI),
        media_type="text/plain",
        size_bytes=len(content),
        digest=content_bytes_digest(content),
    )
    assert store.get(content_bytes_digest(content)) == content


def test_inline_json_with_an_origin_records_its_canonical_json() -> None:
    store = InMemoryContentStore()

    resolved = resolve_input(
        InlineInput(value={"b": [1, 2], "a": "Café"}, origin=InputOrigin(uri=S3_URI)),
        policy=file_policy(),
        store=store,
    )

    content = '{"a":"Café","b":[1,2]}'.encode()

    assert resolved.value == {"b": [1, 2], "a": "Café"}
    assert resolved.provenance is not None
    assert resolved.provenance.digest == content_bytes_digest(content)
    assert store.get(resolved.provenance.digest) == content


def test_inline_json_without_an_origin_still_has_no_provenance() -> None:
    store = InMemoryContentStore()

    resolved = resolve_input(
        InlineInput(value={"a": 1}),
        policy=file_policy(),
        store=store,
    )

    assert resolved.provenance is None
    assert not store.contains(content_bytes_digest(b'{"a":1}'))


def test_provenance_names_a_uri_exactly_when_it_was_a_reference() -> None:
    with pytest.raises(ValidationError, match="A reference's provenance names its URI."):
        InputProvenance(media_type="image/png", size_bytes=1, digest=content_bytes_digest(b"x"))

    with pytest.raises(ValidationError, match="An inline input's provenance has no URI."):
        InputProvenance(
            inline=True,
            uri="file:///x.png",
            media_type="image/png",
            size_bytes=1,
            digest=content_bytes_digest(b"x"),
        )


def test_a_references_provenance_dumps_as_it_always_has() -> None:
    digest = content_bytes_digest(PDF)

    assert InputProvenance(
        uri="file:///scan.pdf",
        media_type="application/pdf",
        size_bytes=len(PDF),
        digest=digest,
    ).model_dump(mode="json") == {
        "uri": "file:///scan.pdf",
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
        "digest": digest,
    }


def test_an_inline_inputs_provenance_dumps_inline_and_its_origin() -> None:
    digest = content_bytes_digest(PDF)

    assert InputProvenance(
        inline=True,
        origin=InputOrigin(uri=S3_URI, etag="9b2c"),
        media_type="application/pdf",
        size_bytes=len(PDF),
        digest=digest,
    ).model_dump(mode="json") == {
        "inline": True,
        "origin": {"uri": S3_URI, "etag": "9b2c"},
        "media_type": "application/pdf",
        "size_bytes": len(PDF),
        "digest": digest,
    }


def test_a_recorded_provenance_reads_back_from_its_dump() -> None:
    provenance = InputProvenance(
        inline=True,
        origin=InputOrigin(uri=S3_URI),
        media_type="image/png",
        size_bytes=len(PNG),
        digest=content_bytes_digest(PNG),
    )

    assert InputProvenance.model_validate(provenance.model_dump(mode="json")) == provenance
