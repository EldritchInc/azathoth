"""Tests for resolving input references at the edge (ADR 0096)."""

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from azathoth.inputs import (
    DEFAULT_MAX_INPUT_BYTES,
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    InputResolver,
    ReferenceInput,
    ResolvedInput,
    content_bytes_digest,
    file_uri,
    resolve_input,
)

CHAPTER = "Mara climbed the stairs of Saint Elmo's Light — again.\n"


def file_policy(
    max_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> InputPolicy:
    """Return a policy accepting local files, as the CLI's does."""

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


class RecordingResolver:
    """Return fixed content and record every URI it was asked to read."""

    def __init__(
        self,
        content: bytes,
    ) -> None:
        self.content = content
        self.uris: list[str] = []

    def read(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> bytes:
        """Return the fixed content."""

        self.uris.append(uri)

        return self.content


def test_default_cap_is_ten_mebibytes() -> None:
    assert DEFAULT_MAX_INPUT_BYTES == 10_485_760


def test_policy_lists_its_accepted_schemes() -> None:
    policy = InputPolicy(
        resolvers={"s3": RecordingResolver(b""), "file": FileInputResolver()},
    )

    assert policy.accepted_schemes == ("file", "s3")
    assert policy.max_bytes == DEFAULT_MAX_INPUT_BYTES


def test_policy_requires_a_positive_cap() -> None:
    with pytest.raises(ValueError, match="positive"):
        InputPolicy(resolvers={}, max_bytes=0)


def test_file_resolver_satisfies_the_protocol() -> None:
    assert isinstance(FileInputResolver(), InputResolver)


def test_file_uri_is_absolute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    uri = file_uri(Path("chapter.md"))

    assert uri.startswith("file:///")
    assert uri == (Path.cwd() / "chapter.md").as_uri()


def test_file_uri_escapes_spaces(
    tmp_path: Path,
) -> None:
    assert "%20" in file_uri(tmp_path / "chapter one.md")


def test_inline_json_resolves_to_its_value_without_provenance() -> None:
    store = InMemoryContentStore()

    resolved = resolve_input(
        InlineInput(value={"text": "hello"}),
        policy=file_policy(),
        store=store,
    )

    assert resolved == ResolvedInput(value={"text": "hello"}, media_type="application/json")
    assert resolved.provenance is None


def test_inline_text_resolves_to_its_string() -> None:
    resolved = resolve_input(
        InlineInput(value="hello", media_type="text/plain"),
        policy=file_policy(),
        store=InMemoryContentStore(),
    )

    assert (resolved.value, resolved.media_type) == ("hello", "text/plain")


def test_inline_input_needs_no_accepted_scheme() -> None:
    resolved = resolve_input(
        InlineInput(value=3),
        policy=InputPolicy(resolvers={}),
        store=InMemoryContentStore(),
    )

    assert resolved.value == 3


def test_text_file_resolves_to_its_string_with_provenance(
    tmp_path: Path,
) -> None:
    content = CHAPTER.encode()
    path = write(tmp_path / "chapter.md", content)
    store = InMemoryContentStore()

    resolved = resolve_input(
        ReferenceInput(uri=file_uri(path), media_type="text/markdown"),
        policy=file_policy(),
        store=store,
    )

    assert resolved.value == CHAPTER
    assert resolved.media_type == "text/markdown"
    assert resolved.provenance == InputProvenance(
        uri=file_uri(path),
        media_type="text/markdown",
        size_bytes=len(content),
        digest=content_bytes_digest(content),
    )


def test_json_file_resolves_to_its_parsed_value(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "request.json", json.dumps({"chapters": [1, 2]}).encode())

    resolved = resolve_input(
        ReferenceInput(uri=file_uri(path), media_type="application/json"),
        policy=file_policy(),
        store=InMemoryContentStore(),
    )

    assert resolved.value == {"chapters": [1, 2]}


def test_resolved_content_is_stored_by_its_digest(
    tmp_path: Path,
) -> None:
    content = CHAPTER.encode()
    path = write(tmp_path / "chapter.md", content)
    store = InMemoryContentStore()

    resolved = resolve_input(
        ReferenceInput(uri=file_uri(path), media_type="text/markdown"),
        policy=file_policy(),
        store=store,
    )

    assert resolved.provenance is not None
    assert store.get(resolved.provenance.digest) == content


def test_the_media_type_comes_from_the_reference_not_the_extension(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "request.json", b'{"a": 1}')

    resolved = resolve_input(
        ReferenceInput(uri=file_uri(path), media_type="text/plain"),
        policy=file_policy(),
        store=InMemoryContentStore(),
    )

    assert resolved.value == '{"a": 1}'


def test_a_reference_is_read_by_the_resolver_for_its_scheme() -> None:
    resolver = RecordingResolver(b"from the bucket")

    resolved = resolve_input(
        ReferenceInput(uri="S3://bucket/key.txt", media_type="text/plain"),
        policy=InputPolicy(resolvers={"s3": resolver}),
        store=InMemoryContentStore(),
    )

    assert resolved.value == "from the bucket"
    assert resolver.uris == ["S3://bucket/key.txt"]


def test_an_unaccepted_scheme_is_refused_before_anything_is_read() -> None:
    resolver = RecordingResolver(b"secret")
    store = InMemoryContentStore()

    with pytest.raises(
        InputResolutionError,
        match=(
            r"Input s3://bucket/key.txt uses the 's3' scheme, which is not accepted here; "
            r"accepted schemes: file\."
        ),
    ):
        resolve_input(
            ReferenceInput(uri="s3://bucket/key.txt", media_type="text/plain"),
            policy=InputPolicy(resolvers={"file": FileInputResolver()}),
            store=store,
        )

    assert resolver.uris == []


def test_a_policy_without_schemes_says_so() -> None:
    with pytest.raises(InputResolutionError, match="no schemes are accepted"):
        resolve_input(
            ReferenceInput(uri="file:///tmp/x.txt", media_type="text/plain"),
            policy=InputPolicy(resolvers={}),
            store=InMemoryContentStore(),
        )


def test_content_over_the_cap_is_refused_and_not_stored(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "big.txt", b"x" * 11)
    store = InMemoryContentStore()

    with pytest.raises(
        InputResolutionError,
        match="is larger than the limit of 10 bytes",
    ):
        resolve_input(
            ReferenceInput(uri=file_uri(path), media_type="text/plain"),
            policy=file_policy(max_bytes=10),
            store=store,
        )

    assert not store.contains(content_bytes_digest(b"x" * 11))


def test_content_at_the_cap_is_accepted(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "exact.txt", b"x" * 10)

    resolved = resolve_input(
        ReferenceInput(uri=file_uri(path), media_type="text/plain"),
        policy=file_policy(max_bytes=10),
        store=InMemoryContentStore(),
    )

    assert resolved.value == "x" * 10


def test_a_resolver_returning_too_much_is_refused() -> None:
    with pytest.raises(InputResolutionError, match="is larger than the limit of 4 bytes"):
        resolve_input(
            ReferenceInput(uri="s3://bucket/key.txt", media_type="text/plain"),
            policy=InputPolicy(resolvers={"s3": RecordingResolver(b"12345")}, max_bytes=4),
            store=InMemoryContentStore(),
        )


def test_the_file_resolver_refuses_a_file_over_the_cap(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "big.txt", b"x" * 1000)

    with pytest.raises(InputResolutionError, match="is larger than the limit of 10 bytes"):
        FileInputResolver().read(file_uri(path), max_bytes=10)


def test_content_that_does_not_decode_is_refused_and_not_stored(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "broken.json", b"{not json")
    store = InMemoryContentStore()

    with pytest.raises(InputResolutionError, match="Content is not valid JSON"):
        resolve_input(
            ReferenceInput(uri=file_uri(path), media_type="application/json"),
            policy=file_policy(),
            store=store,
        )

    assert not store.contains(content_bytes_digest(b"{not json"))


def test_a_missing_file_is_refused(
    tmp_path: Path,
) -> None:
    uri = file_uri(tmp_path / "missing.md")

    with pytest.raises(InputResolutionError, match=f"Input {uri} does not exist."):
        FileInputResolver().read(uri, max_bytes=DEFAULT_MAX_INPUT_BYTES)


def test_a_directory_is_refused(
    tmp_path: Path,
) -> None:
    uri = file_uri(tmp_path)

    with pytest.raises(InputResolutionError, match="is not a file"):
        FileInputResolver().read(uri, max_bytes=DEFAULT_MAX_INPUT_BYTES)


def test_localhost_names_the_local_host(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "chapter.md", b"local")
    uri = file_uri(path).replace("file://", "file://localhost", 1)

    assert FileInputResolver().read(uri, max_bytes=DEFAULT_MAX_INPUT_BYTES) == b"local"


def test_a_remote_host_is_refused() -> None:
    with pytest.raises(InputResolutionError, match="must name the local host"):
        FileInputResolver().read(
            "file://fileserver/share/chapter.md",
            max_bytes=DEFAULT_MAX_INPUT_BYTES,
        )


def test_a_relative_file_uri_is_refused() -> None:
    with pytest.raises(InputResolutionError, match="must name an absolute path"):
        FileInputResolver().read("file:chapter.md", max_bytes=DEFAULT_MAX_INPUT_BYTES)


def test_the_file_resolver_reads_only_file_uris() -> None:
    with pytest.raises(InputResolutionError, match="is not a file:// URI"):
        FileInputResolver().read("s3://bucket/key", max_bytes=DEFAULT_MAX_INPUT_BYTES)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_an_unreadable_file_is_refused(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "secret.txt", b"secret")
    path.chmod(0)

    try:
        if os.access(path, os.R_OK):
            pytest.skip("running with permission to read any file")

        with pytest.raises(InputResolutionError, match="Unable to read input"):
            FileInputResolver().read(file_uri(path), max_bytes=DEFAULT_MAX_INPUT_BYTES)
    finally:
        path.chmod(0o600)


def test_a_file_path_with_spaces_round_trips(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "chapter one.md", b"one")

    assert FileInputResolver().read(file_uri(path), max_bytes=DEFAULT_MAX_INPUT_BYTES) == b"one"


def test_resolution_errors_are_value_errors() -> None:
    assert issubclass(InputResolutionError, ValueError)


def test_provenance_requires_a_digest() -> None:
    with pytest.raises(ValidationError):
        InputProvenance(uri="file:///x", media_type="text/plain", size_bytes=1, digest="abc")


def test_provenance_serializes_in_its_recorded_order() -> None:
    provenance = InputProvenance(
        uri="file:///x.md",
        media_type="text/markdown",
        size_bytes=3,
        digest=content_bytes_digest(b"abc"),
    )

    assert list(provenance.model_dump(mode="json")) == ["uri", "media_type", "size_bytes", "digest"]
