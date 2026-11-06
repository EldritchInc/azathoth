"""Tests that the guides describe binary inputs as they really behave (ADR 0112)."""

import json
import re
from pathlib import Path

import pytest

from azathoth.inputs import (
    BINARY_MEDIA_TYPES,
    MEDIA_TYPES_BY_EXTENSION,
    ContentRef,
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputPolicy,
    InputResolutionError,
    ReferenceInput,
    content_ref_from_value,
    decode_input_source,
    resolve_input,
)

ROOT = Path(__file__).parents[2]

INPUTS_README = ROOT / "src" / "azathoth" / "inputs" / "README.md"

CLI_README = ROOT / "src" / "azathoth" / "cli" / "README.md"

CONCEPTS = ROOT / "docs" / "concepts.md"

ADR = ROOT / "docs" / "adrs" / "0112-accept-binary-inputs.md"


def json_blocks(
    path: Path,
) -> list[str]:
    """Return the JSON blocks of one document."""

    return re.findall(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)


def text_blocks(
    path: Path,
) -> list[str]:
    """Return the text blocks of one document."""

    return re.findall(r"```text\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)


@pytest.mark.parametrize("path", [INPUTS_README, CLI_README, CONCEPTS, ADR])
def test_every_documented_content_handle_is_one(
    path: Path,
) -> None:
    handles = [
        json.loads(block)
        for block in json_blocks(path)
        if block.lstrip().startswith('{"content"') or block.startswith('{\n  "content"')
    ]

    assert handles, path

    for handle in handles:
        fields = dict(handle["content"])
        fields["digest"] = "0" * 64

        assert content_ref_from_value({"content": fields}) == ContentRef.model_validate(fields)


def test_the_documented_inline_document_decodes_and_resolves() -> None:
    (block,) = [block for block in json_blocks(INPUTS_README) if '"origin"' in block]

    source = decode_input_source(json.loads(block))

    assert isinstance(source, InlineInput)

    #
    # The documented value is the start of a PDF, header and all, so it
    # resolves to a handle.
    #
    resolved = resolve_input(source, policy=InputPolicy(), store=InMemoryContentStore())

    assert resolved.provenance is not None
    assert resolved.provenance.origin == source.origin


def test_the_cli_readme_maps_every_binary_extension() -> None:
    text = CLI_README.read_text(encoding="utf-8")

    for extension, media_type in MEDIA_TYPES_BY_EXTENSION.items():
        if media_type in BINARY_MEDIA_TYPES:
            assert re.search(rf"\{extension}\b[^\n]*{re.escape(media_type)}", text), extension


def test_the_cli_readme_quotes_the_signature_refusal_of_a_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "claim.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(InputResolutionError) as raised:
        resolve_input(
            ReferenceInput(uri=path.as_uri(), media_type="application/pdf"),
            policy=InputPolicy(resolvers={"file": FileInputResolver()}),
            store=InMemoryContentStore(),
        )

    documented = str(raised.value).replace(path.as_uri(), "file:///Users/you/claim.pdf")

    assert any(documented in block.splitlines() for block in text_blocks(CLI_README))


def test_the_cli_readme_shows_an_input_provenance_block() -> None:
    (block,) = [block for block in text_blocks(CLI_README) if block.startswith("Input Provenance:")]

    provenance = json.loads(block.removeprefix("Input Provenance:\n"))

    assert provenance["origin"]["uri"] == provenance["uri"]
    assert set(provenance) == {"uri", "origin", "media_type", "size_bytes", "digest"}
