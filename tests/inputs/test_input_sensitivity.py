"""Tests that an input source may name its sensitivity, and keeps it once resolved (ADR 0123)."""

import base64
import json
from pathlib import Path

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.inputs import (
    FileInputResolver,
    InlineInput,
    InMemoryContentStore,
    InputPolicy,
    InputSourceError,
    ReferenceInput,
    decode_input_source,
    file_uri,
    resolve_input,
)
from azathoth.inputs.source import SENSITIVITY_KEY
from azathoth.sensitivity import Sensitivity

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

POLICY = InputPolicy(resolvers={"file": FileInputResolver()})


def test_the_label_key_is_sensitivity() -> None:
    assert SENSITIVITY_KEY == "sensitivity"


# Sources


@pytest.mark.parametrize("label", list(Sensitivity))
def test_an_inline_source_names_its_label(
    label: Sensitivity,
) -> None:
    source = decode_input_source({"value": {"claim": 412}, "sensitivity": label.value})

    assert source == InlineInput(value={"claim": 412}, sensitivity=label)


def test_a_reference_names_its_label() -> None:
    source = decode_input_source(
        {"uri": "s3://claims/412.pdf", "media_type": "application/pdf", "sensitivity": "restricted"}
    )

    assert source == ReferenceInput(
        uri="s3://claims/412.pdf",
        media_type="application/pdf",
        sensitivity=Sensitivity.RESTRICTED,
    )


def test_a_source_without_a_label_has_none() -> None:
    assert InlineInput(value=1).sensitivity is None
    assert ReferenceInput(uri="file:///a.txt", media_type="text/plain").sensitivity is None


def test_an_unknown_label_is_refused() -> None:
    with pytest.raises(InputSourceError) as caught:
        decode_input_source({"value": 1, "sensitivity": "secret"})

    assert str(caught.value) == (
        "An input's sensitivity is 'public', 'internal' or 'restricted'; got 'secret'."
    )

    with pytest.raises(InputSourceError) as reference:
        decode_input_source({"uri": "file:///a.txt", "media_type": "text/plain", "sensitivity": 2})

    assert str(reference.value) == (
        "An input's sensitivity is 'public', 'internal' or 'restricted'; got 2."
    )

    with pytest.raises(ValidationError):
        InlineInput.model_validate({"value": 1, "sensitivity": "secret"})


def test_an_unlabelled_source_dumps_as_it_did_before_labels() -> None:
    assert InlineInput(value=1).model_dump(mode="json") == {
        "value": 1,
        "media_type": "application/json",
    }
    assert ReferenceInput(uri="file:///a.txt", media_type="text/plain").model_dump(mode="json") == {
        "uri": "file:///a.txt",
        "media_type": "text/plain",
    }


def test_a_labelled_source_dumps_its_label_and_reads_back() -> None:
    inline = InlineInput(value=1, sensitivity=Sensitivity.RESTRICTED)
    reference = ReferenceInput(
        uri="file:///a.txt",
        media_type="text/plain",
        sensitivity=Sensitivity.PUBLIC,
    )

    assert inline.model_dump(mode="json")["sensitivity"] == "restricted"
    assert reference.model_dump(mode="json")["sensitivity"] == "public"
    assert decode_input_source(json.loads(inline.model_dump_json())) == inline
    assert decode_input_source(json.loads(reference.model_dump_json())) == reference


# Resolution


def test_a_plain_inline_input_keeps_its_label_and_has_no_provenance() -> None:
    resolved = resolve_input(
        InlineInput(value={"claim": 412}, sensitivity=Sensitivity.RESTRICTED),
        policy=POLICY,
        store=InMemoryContentStore(),
    )

    assert resolved.value == {"claim": 412}
    assert resolved.provenance is None
    assert resolved.sensitivity is Sensitivity.RESTRICTED


def test_a_binary_inline_input_keeps_its_label() -> None:
    resolved = resolve_input(
        InlineInput(
            value=base64.b64encode(PDF).decode("ascii"),
            media_type="application/pdf",
            sensitivity=Sensitivity.RESTRICTED,
        ),
        policy=POLICY,
        store=InMemoryContentStore(),
    )

    assert resolved.provenance is not None
    assert resolved.sensitivity is Sensitivity.RESTRICTED


def test_a_reference_keeps_its_label(
    tmp_path: Path,
) -> None:
    path = tmp_path / "claim.txt"
    path.write_text("Claim 412.", encoding="utf-8")

    resolved = resolve_input(
        ReferenceInput(
            uri=file_uri(path),
            media_type="text/plain",
            sensitivity=Sensitivity.PUBLIC,
        ),
        policy=POLICY,
        store=InMemoryContentStore(),
    )

    assert resolved.value == "Claim 412."
    assert resolved.sensitivity is Sensitivity.PUBLIC


def test_an_unlabelled_input_resolves_with_no_label() -> None:
    resolved = resolve_input(InlineInput(value=1), policy=POLICY, store=InMemoryContentStore())

    assert resolved.sensitivity is None


def test_the_documented_source_refusals_are_the_ones_given() -> None:
    readme = (Path(__file__).parents[2] / "src" / "azathoth" / "inputs" / "README.md").read_text(
        encoding="utf-8"
    )

    refused: tuple[JsonValue, ...] = (
        {"value": 1, "size": 2},
        {"value": 1, "sensitivity": "secret"},
    )

    for data in refused:
        with pytest.raises(InputSourceError) as caught:
            decode_input_source(data)

        assert f"\n{caught.value}\n" in readme
