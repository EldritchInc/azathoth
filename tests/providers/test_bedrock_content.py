"""Tests that Bedrock is sent the content a prompt shows, as Converse blocks (ADR 0115)."""

import asyncio

import pytest

from azathoth.inputs import ContentRef, content_bytes_digest
from azathoth.providers import (
    BEDROCK_IMAGE_FORMATS,
    BEDROCK_MAX_DOCUMENT_BYTES,
    BEDROCK_MAX_DOCUMENTS,
    BEDROCK_MAX_IMAGE_BYTES,
    BEDROCK_MAX_IMAGES,
    BedrockConfiguration,
    BedrockLanguageModel,
    BedrockModelDirectory,
    BedrockPricing,
    ContentPart,
    ModelCapability,
    ModelModality,
    Prompt,
    PromptContentError,
    TextPart,
    UnsupportedModelRequestError,
    bedrock_content,
    giving_prompt_content,
)
from tests.providers.fake_bedrock import FakeBedrockClient, foundation_model

MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"

NOVA_PRO = "amazon.nova-pro-v1:0"

PDF = b"%PDF-1.7\n%%EOF\n"

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"

WEBP = b"RIFF\x0c\x00\x00\x00WEBPVP8 "


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

PHOTO = handle(PNG, "image/png")

SNAPSHOT = handle(JPEG, "image/jpeg")

STICKER = handle(WEBP, "image/webp")


def content(
    prompt: Prompt,
    given: dict[str, bytes],
) -> list[dict[str, object]]:
    """Return the blocks one prompt is sent as, with some bytes given."""

    with giving_prompt_content(given):
        return bedrock_content(MODEL, prompt)


def refusal(
    prompt: Prompt,
    given: dict[str, bytes],
) -> tuple[str, list[tuple[str, ...]]]:
    """Return what a Bedrock model refuses a prompt with, and the calls it made."""

    client = FakeBedrockClient()

    with giving_prompt_content(given), pytest.raises(UnsupportedModelRequestError) as raised:
        asyncio.run(BedrockLanguageModel(client, MODEL).complete(prompt))

    return str(raised.value), client.calls


def test_a_prompt_of_text_is_one_text_block_as_it_always_was() -> None:
    assert bedrock_content(MODEL, Prompt(text="How many?")) == [{"text": "How many?"}]


def test_parts_are_blocks_in_order_with_their_raw_bytes() -> None:
    prompt = Prompt(
        parts=(
            TextPart(text="Here is the claim form:\n"),
            ContentPart(content=DOCUMENT),
            TextPart(text="\nand the photos:\n"),
            ContentPart(content=PHOTO),
            ContentPart(content=SNAPSHOT),
            ContentPart(content=STICKER),
        )
    )
    given = {
        DOCUMENT.digest: PDF,
        PHOTO.digest: PNG,
        SNAPSHOT.digest: JPEG,
        STICKER.digest: WEBP,
    }

    assert content(prompt, given) == [
        {"text": "Here is the claim form:\n"},
        {"document": {"format": "pdf", "name": "document-1", "source": {"bytes": PDF}}},
        {"text": "\nand the photos:\n"},
        {"image": {"format": "png", "source": {"bytes": PNG}}},
        {"image": {"format": "jpeg", "source": {"bytes": JPEG}}},
        {"image": {"format": "webp", "source": {"bytes": WEBP}}},
    ]


def test_every_image_media_type_has_a_converse_format() -> None:
    assert BEDROCK_IMAGE_FORMATS == {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/webp": "webp",
    }


def test_documents_are_named_neutrally_in_the_order_they_are_shown() -> None:
    other = b"%PDF-1.7\n% another\n%%EOF\n"
    prompt = Prompt(
        parts=(
            TextPart(text="Compare:"),
            ContentPart(content=DOCUMENT),
            ContentPart(content=handle(other, "application/pdf")),
            ContentPart(content=DOCUMENT),
        )
    )
    blocks = content(prompt, {DOCUMENT.digest: PDF, content_bytes_digest(other): other})
    names: list[object] = []

    for block in blocks[1:]:
        document = block["document"]

        assert isinstance(document, dict)

        names.append(document["name"])

    assert names == ["document-1", "document-2", "document-3"]


def test_the_limits_are_converses_own() -> None:
    assert (BEDROCK_MAX_IMAGES, BEDROCK_MAX_DOCUMENTS) == (20, 5)
    assert (BEDROCK_MAX_IMAGE_BYTES, BEDROCK_MAX_DOCUMENT_BYTES) == (3_750_000, 4_500_000)


def test_a_model_is_sent_the_blocks_of_the_content_it_is_shown() -> None:
    client = FakeBedrockClient(
        replies={
            MODEL: [
                {
                    "output": {"message": {"role": "assistant", "content": [{"text": "A cat."}]}},
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1290, "outputTokens": 2, "totalTokens": 1292},
                    "metrics": {"latencyMs": 300},
                }
            ]
        }
    )
    prompt = Prompt(parts=(TextPart(text="What is this?"), ContentPart(content=PHOTO)))

    with giving_prompt_content({PHOTO.digest: PNG}):
        response = asyncio.run(BedrockLanguageModel(client, MODEL).complete(prompt))

    assert response.text == "A cat."
    assert client.calls == [("converse", MODEL, "What is this?")]
    assert client.contents == [
        [{"text": "What is this?"}, {"image": {"format": "png", "source": {"bytes": PNG}}}]
    ]


def test_content_whose_bytes_were_not_given_is_refused_and_nothing_is_sent() -> None:
    client = FakeBedrockClient()

    with pytest.raises(PromptContentError) as raised:
        asyncio.run(
            BedrockLanguageModel(client, MODEL).complete(
                Prompt(parts=(ContentPart(content=PHOTO),))
            )
        )

    assert str(raised.value) == (
        f"Model bedrock/{MODEL} was not given the bytes of content {PHOTO.digest}."
    )
    assert client.calls == []


def images(
    count: int,
) -> tuple[Prompt, dict[str, bytes]]:
    """Return a prompt showing some distinct images, and their bytes."""

    shown = [PNG + bytes([index]) for index in range(count)]

    return (
        Prompt(
            parts=(
                TextPart(text="Look:"),
                *(ContentPart(content=handle(image, "image/png")) for image in shown),
            )
        ),
        {content_bytes_digest(image): image for image in shown},
    )


def documents(
    count: int,
) -> tuple[Prompt, dict[str, bytes]]:
    """Return a prompt showing some distinct PDFs, and their bytes."""

    shown = [PDF + bytes([index]) for index in range(count)]

    return (
        Prompt(
            parts=(
                TextPart(text="Read:"),
                *(ContentPart(content=handle(document, "application/pdf")) for document in shown),
            )
        ),
        {content_bytes_digest(document): document for document in shown},
    )


def test_twenty_images_are_sent() -> None:
    assert len(content(*images(20))) == 21


def test_more_than_twenty_images_are_refused_before_anything_is_sent() -> None:
    assert refusal(*images(21)) == (
        f"Bedrock model {MODEL!r} is shown at most 20 images in one prompt; this one shows 21.",
        [],
    )


def test_five_documents_are_sent() -> None:
    assert len(content(*documents(5))) == 6


def test_more_than_five_documents_are_refused_before_anything_is_sent() -> None:
    assert refusal(*documents(6)) == (
        f"Bedrock model {MODEL!r} is shown at most 5 documents in one prompt; this one shows 6.",
        [],
    )


def test_an_image_of_the_largest_size_is_sent() -> None:
    image = PNG + b"\x00" * (BEDROCK_MAX_IMAGE_BYTES - len(PNG))
    shown = handle(image, "image/png")

    assert len(content(Prompt(parts=(ContentPart(content=shown),)), {shown.digest: image})) == 1


def test_a_larger_image_is_refused_before_anything_is_sent() -> None:
    image = PNG + b"\x00" * (BEDROCK_MAX_IMAGE_BYTES - len(PNG) + 1)
    shown = handle(image, "image/png")

    assert refusal(Prompt(parts=(ContentPart(content=shown),)), {shown.digest: image}) == (
        f"Bedrock model {MODEL!r} is shown images of at most 3750000 bytes; "
        f"content {shown.digest} is 3750001.",
        [],
    )


def test_a_document_of_the_largest_size_is_sent() -> None:
    document = PDF + b"\x00" * (BEDROCK_MAX_DOCUMENT_BYTES - len(PDF))
    shown = handle(document, "application/pdf")
    prompt = Prompt(parts=(TextPart(text="Read:"), ContentPart(content=shown)))

    assert len(content(prompt, {shown.digest: document})) == 2


def test_a_larger_document_is_refused_before_anything_is_sent() -> None:
    document = PDF + b"\x00" * (BEDROCK_MAX_DOCUMENT_BYTES - len(PDF) + 1)
    shown = handle(document, "application/pdf")
    prompt = Prompt(parts=(TextPart(text="Read:"), ContentPart(content=shown)))

    assert refusal(prompt, {shown.digest: document}) == (
        f"Bedrock model {MODEL!r} is shown documents of at most 4500000 bytes; "
        f"content {shown.digest} is 4500001.",
        [],
    )


def test_a_document_with_no_text_beside_it_is_refused_before_anything_is_sent() -> None:
    assert refusal(Prompt(parts=(ContentPart(content=DOCUMENT),)), {DOCUMENT.digest: PDF}) == (
        f"Bedrock model {MODEL!r} is shown a document only beside text; this prompt has none.",
        [],
    )


def test_an_image_needs_no_text_beside_it() -> None:
    assert content(Prompt(parts=(ContentPart(content=PHOTO),)), {PHOTO.digest: PNG}) == [
        {"image": {"format": "png", "source": {"bytes": PNG}}}
    ]


def discovered(
    pricing: BedrockPricing,
    *inputs: str,
) -> tuple[frozenset[ModelModality], frozenset[ModelCapability]]:
    """Return the input modalities and capabilities discovered for Nova Pro."""

    client = FakeBedrockClient(foundation_models=[foundation_model(NOVA_PRO, inputs=inputs)])
    (model,) = asyncio.run(
        BedrockModelDirectory(
            BedrockConfiguration(region="us-east-1", pricing=pricing),
            client,
        ).models()
    )

    return model.input_modalities, model.capabilities


def test_the_pricing_document_adds_the_file_modality_bedrock_does_not_report() -> None:
    pricing = BedrockPricing.model_validate({"input_modalities": {NOVA_PRO: ["file"]}})

    assert discovered(pricing, "TEXT", "IMAGE") == (
        frozenset({ModelModality.TEXT, ModelModality.IMAGE, ModelModality.FILE}),
        frozenset({ModelCapability.STREAMING, ModelCapability.VISION}),
    )


def test_an_added_image_modality_makes_a_model_one_with_vision() -> None:
    pricing = BedrockPricing.model_validate({"input_modalities": {NOVA_PRO: ["image"]}})

    assert discovered(pricing, "TEXT") == (
        frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
        frozenset({ModelCapability.STREAMING, ModelCapability.VISION}),
    )


def test_the_pricing_document_never_takes_away_a_modality_bedrock_reports() -> None:
    pricing = BedrockPricing.model_validate({"input_modalities": {NOVA_PRO: ["file"]}})

    assert ModelModality.IMAGE in discovered(pricing, "TEXT", "IMAGE")[0]


def test_a_model_the_document_does_not_name_keeps_what_bedrock_reports() -> None:
    pricing = BedrockPricing.model_validate({"input_modalities": {"other.model": ["file"]}})

    assert discovered(pricing, "TEXT")[0] == frozenset({ModelModality.TEXT})


def test_a_model_may_be_declared_to_read_files_without_being_priced() -> None:
    pricing = BedrockPricing.model_validate({"version": 1, "input_modalities": {MODEL: ["file"]}})

    assert pricing.price(MODEL) is None
    assert pricing.added_input_modalities(MODEL) == frozenset({ModelModality.FILE})
    assert pricing.added_input_modalities(NOVA_PRO) == frozenset()


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"input_modalities": {NOVA_PRO: ["pdf"]}}, id="unknown-modality"),
        pytest.param({"input_modalities": {"": ["file"]}}, id="empty-model-id"),
        pytest.param({"input_modalities": {NOVA_PRO: "file"}}, id="not-a-list"),
    ],
)
def test_declared_modalities_are_validated(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        BedrockPricing.model_validate(value)
