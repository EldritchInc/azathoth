"""Tests that OpenRouter is sent the content a prompt shows, in its own parts (ADR 0115)."""

import asyncio
import base64
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from azathoth.inputs import ContentRef, content_bytes_digest
from azathoth.providers import (
    OPENROUTER_PDF_ENGINE,
    ContentPart,
    OpenRouterConfiguration,
    OpenRouterLanguageModel,
    Prompt,
    PromptContentError,
    TextPart,
    giving_prompt_content,
    openrouter_request,
)

MODEL = "google/gemini-vision"

PDF = b"%PDF-1.7\n%%EOF\n"

OTHER_PDF = b"%PDF-1.7\n% another\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"


def handle(
    content: bytes,
    media_type: str,
) -> ContentRef:
    """Return the handle of some content."""

    return ContentRef(
        digest=content_bytes_digest(content),
        media_type=media_type,
        size_bytes=len(content),
    )


DOCUMENT = handle(PDF, "application/pdf")

OTHER_DOCUMENT = handle(OTHER_PDF, "application/pdf")

PHOTO = handle(PNG, "image/png")

SNAPSHOT = handle(JPEG, "image/jpeg")

GIVEN = {
    DOCUMENT.digest: PDF,
    OTHER_DOCUMENT.digest: OTHER_PDF,
    PHOTO.digest: PNG,
    SNAPSHOT.digest: JPEG,
}


def data_url(
    content: bytes,
    media_type: str,
) -> str:
    """Return the data URL OpenRouter is given some content in."""

    return f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"


def request(
    prompt: Prompt,
) -> dict[str, Any]:
    """Return the request one prompt is sent as, with every test content given."""

    with giving_prompt_content(GIVEN):
        return openrouter_request(MODEL, prompt)


def test_a_prompt_of_text_is_sent_as_it_always_was() -> None:
    assert openrouter_request(MODEL, Prompt(text="Classify this ticket.")) == {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Classify this ticket."}],
    }


def test_an_image_is_sent_as_an_image_url_part_beside_text() -> None:
    prompt = Prompt(
        parts=(
            TextPart(text="What is in this photo?\n"),
            ContentPart(content=PHOTO),
        )
    )

    assert request(prompt) == {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this photo?\n"},
                    {"type": "image_url", "image_url": {"url": data_url(PNG, "image/png")}},
                ],
            }
        ],
    }


def test_a_pdf_is_sent_as_a_file_part_read_by_the_models_own_engine() -> None:
    prompt = Prompt(
        parts=(
            TextPart(text="Summarize:\n"),
            ContentPart(content=DOCUMENT),
        )
    )

    assert request(prompt) == {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Summarize:\n"},
                    {
                        "type": "file",
                        "file": {
                            "filename": "document-1.pdf",
                            "file_data": data_url(PDF, "application/pdf"),
                        },
                    },
                ],
            }
        ],
        "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
    }


def test_the_pdf_engine_is_the_models_own() -> None:
    assert OPENROUTER_PDF_ENGINE == "native"


def test_parts_are_sent_in_order_and_pdfs_are_numbered_in_order() -> None:
    prompt = Prompt(
        parts=(
            ContentPart(content=SNAPSHOT),
            TextPart(text=" then "),
            ContentPart(content=DOCUMENT),
            ContentPart(content=PHOTO),
            ContentPart(content=OTHER_DOCUMENT),
            ContentPart(content=DOCUMENT),
        )
    )
    content = request(prompt)["messages"][0]["content"]

    assert [part["type"] for part in content] == [
        "image_url",
        "text",
        "file",
        "image_url",
        "file",
        "file",
    ]
    assert content[0]["image_url"]["url"] == data_url(JPEG, "image/jpeg")
    assert [
        (part["file"]["filename"], part["file"]["file_data"])
        for part in content
        if part["type"] == "file"
    ] == [
        ("document-1.pdf", data_url(PDF, "application/pdf")),
        ("document-2.pdf", data_url(OTHER_PDF, "application/pdf")),
        ("document-3.pdf", data_url(PDF, "application/pdf")),
    ]


def test_a_request_with_images_alone_names_no_pdf_engine() -> None:
    prompt = Prompt(parts=(ContentPart(content=PHOTO), ContentPart(content=SNAPSHOT)))

    assert "plugins" not in request(prompt)


def test_content_whose_bytes_were_not_given_is_refused() -> None:
    with giving_prompt_content({PHOTO.digest: PNG}), pytest.raises(PromptContentError) as raised:
        openrouter_request(MODEL, Prompt(parts=(ContentPart(content=DOCUMENT),)))

    assert str(raised.value) == (
        f"Model openrouter/{MODEL} was not given the bytes of content {DOCUMENT.digest}."
    )


def openrouter(
    sent: list[httpx.Request],
) -> OpenRouterLanguageModel:
    """Return an OpenRouter model whose transport records each request and replies."""

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)

        return httpx.Response(
            200,
            json={
                "id": "generation-1",
                "model": MODEL,
                "choices": [{"message": {"role": "assistant", "content": "A cat."}}],
                "usage": {
                    "prompt_tokens": 1290,
                    "completion_tokens": 2,
                    "total_tokens": 1292,
                    "cost": 0.0004,
                },
            },
            request=request,
        )

    return OpenRouterLanguageModel(
        OpenRouterConfiguration(
            api_key=SecretStr("test-openrouter-key"),
            base_url="https://openrouter.test/api/v1",
            timeout_seconds=10.0,
        ),
        MODEL,
        transport=httpx.MockTransport(handler),
    )


def test_a_model_is_sent_the_content_it_is_shown() -> None:
    sent: list[httpx.Request] = []
    prompt = Prompt(parts=(TextPart(text="What is this?"), ContentPart(content=PHOTO)))

    with giving_prompt_content({PHOTO.digest: PNG}):
        response = asyncio.run(openrouter(sent).complete(prompt))

    (sent_request,) = sent

    assert response.text == "A cat."
    assert json.loads(sent_request.content) == {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image_url", "image_url": {"url": data_url(PNG, "image/png")}},
                ],
            }
        ],
    }


def test_a_model_not_given_the_bytes_is_sent_nothing() -> None:
    sent: list[httpx.Request] = []

    with pytest.raises(PromptContentError):
        asyncio.run(openrouter(sent).complete(Prompt(parts=(ContentPart(content=PHOTO),))))

    assert sent == []
