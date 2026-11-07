"""Tests for prompts of parts: text and the content a model is shown (ADR 0115)."""

import asyncio
import json
from types import MappingProxyType

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.inputs import ContentRef, content_bytes_digest
from azathoth.providers import (
    ContentPart,
    DeterministicLanguageModel,
    Prompt,
    PromptContentError,
    TextPart,
    giving_prompt_content,
    prompt_content_bytes,
)

PDF = b"%PDF-1.7\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

DOCUMENT = ContentRef(
    digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    size_bytes=len(PDF),
)

PHOTO = ContentRef(
    digest=content_bytes_digest(PNG),
    media_type="image/png",
    size_bytes=len(PNG),
)

SHOWING = Prompt(
    parts=(
        TextPart(text="Here is the claim form:\n"),
        ContentPart(content=DOCUMENT),
        TextPart(text="\nand the photo of the damage:\n"),
        ContentPart(content=PHOTO),
        TextPart(text="\nDoes the photo match the form?"),
    )
)


def test_a_prompt_of_text_serializes_as_it_always_did() -> None:
    prompt = Prompt(text="Classify this ticket.")

    assert prompt.model_dump(mode="json") == {"text": "Classify this ticket."}
    assert json.loads(prompt.model_dump_json()) == {"text": "Classify this ticket."}


def test_an_empty_text_prompt_is_still_a_prompt() -> None:
    assert Prompt(text="").model_dump(mode="json") == {"text": ""}


def test_a_prompt_of_parts_serializes_its_parts_and_no_text() -> None:
    dumped = SHOWING.model_dump(mode="json")

    assert dumped == {
        "parts": [
            {"text": "Here is the claim form:\n"},
            {"content": DOCUMENT.model_dump(mode="json")},
            {"text": "\nand the photo of the damage:\n"},
            {"content": PHOTO.model_dump(mode="json")},
            {"text": "\nDoes the photo match the form?"},
        ]
    }
    assert Prompt.model_validate(dumped) == SHOWING


def test_a_content_part_is_a_content_handle() -> None:
    assert ContentPart(content=DOCUMENT).model_dump(mode="json") == DOCUMENT.to_value()


def test_a_prompt_names_its_content_and_its_text_in_order() -> None:
    assert SHOWING.contents() == (DOCUMENT, PHOTO)
    assert SHOWING.text_parts() == (
        "Here is the claim form:\n",
        "\nand the photo of the damage:\n",
        "\nDoes the photo match the form?",
    )
    assert Prompt(text="Only text.").contents() == ()
    assert Prompt(text="Only text.").text_parts() == ("Only text.",)


def test_content_shown_twice_is_named_twice() -> None:
    prompt = Prompt(parts=(ContentPart(content=PHOTO), ContentPart(content=PHOTO)))

    assert prompt.contents() == (PHOTO, PHOTO)
    assert prompt.text_parts() == ()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        pytest.param(
            {},
            "A prompt holds its text, or parts that show content.",
            id="nothing",
        ),
        pytest.param(
            {"parts": []},
            "A prompt holds its text, or parts that show content.",
            id="no-parts",
        ),
        pytest.param(
            {"text": "", "parts": [{"content": DOCUMENT.model_dump(mode="json")}]},
            "A prompt holds its text or its parts, not both.",
            id="both",
        ),
        pytest.param(
            {"parts": [{"text": "Hello."}, {"text": "Again."}]},
            "A prompt's parts show content; a prompt of text alone holds it as its text.",
            id="text-parts-only",
        ),
        pytest.param(
            {"parts": [{"text": ""}, {"content": DOCUMENT.model_dump(mode="json")}]},
            "at least 1 character",
            id="empty-text-part",
        ),
        pytest.param(
            {"parts": [{"text": "Hello.", "content": DOCUMENT.model_dump(mode="json")}]},
            "Extra inputs are not permitted",
            id="part-of-both",
        ),
        pytest.param(
            {
                "parts": [
                    {"content": {"digest": "0" * 64, "media_type": "text/plain", "size_bytes": 1}}
                ]
            },
            "is not a binary media type",
            id="text-content",
        ),
    ],
)
def test_a_prompt_is_text_or_parts_that_show_content(
    value: dict[str, JsonValue],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        Prompt.model_validate(value)

    assert message in str(raised.value)


def test_a_provider_reads_the_bytes_it_was_given_by_digest() -> None:
    with giving_prompt_content({DOCUMENT.digest: PDF}):
        assert prompt_content_bytes(DOCUMENT, model="openrouter/vision") == PDF


def test_a_provider_cannot_read_bytes_it_was_not_given() -> None:
    with giving_prompt_content({DOCUMENT.digest: PDF}), pytest.raises(PromptContentError) as raised:
        prompt_content_bytes(PHOTO, model="openrouter/vision")

    assert str(raised.value) == (
        f"Model openrouter/vision was not given the bytes of content {PHOTO.digest}."
    )


def test_given_bytes_last_only_for_their_block() -> None:
    with giving_prompt_content({DOCUMENT.digest: PDF}):
        with giving_prompt_content({PHOTO.digest: PNG}):
            assert prompt_content_bytes(PHOTO, model="m") == PNG

            with pytest.raises(PromptContentError):
                prompt_content_bytes(DOCUMENT, model="m")

        assert prompt_content_bytes(DOCUMENT, model="m") == PDF

    with pytest.raises(PromptContentError):
        prompt_content_bytes(DOCUMENT, model="m")


def test_given_bytes_are_a_copy_that_cannot_be_changed() -> None:
    contents = {DOCUMENT.digest: PDF}

    with giving_prompt_content(contents) as given:
        contents[PHOTO.digest] = PNG

        assert isinstance(given, MappingProxyType)
        assert dict(given) == {DOCUMENT.digest: PDF}

        with pytest.raises(PromptContentError):
            prompt_content_bytes(PHOTO, model="m")


def test_the_deterministic_model_reads_what_it_is_shown() -> None:
    model = DeterministicLanguageModel(response_text="It matches.")

    with giving_prompt_content({DOCUMENT.digest: PDF, PHOTO.digest: PNG}):
        response = asyncio.run(model.complete(SHOWING))

    assert response.text == "It matches."
    assert response.prompt_tokens == 17


def test_the_deterministic_model_fails_on_content_it_was_not_given() -> None:
    model = DeterministicLanguageModel()

    with giving_prompt_content({DOCUMENT.digest: PDF}), pytest.raises(PromptContentError) as raised:
        asyncio.run(model.complete(SHOWING))

    assert str(raised.value) == (
        f"Model deterministic/deterministic was not given the bytes of content {PHOTO.digest}."
    )
