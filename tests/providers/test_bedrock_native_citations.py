"""Tests that Bedrock is asked for, and returns, its own citations of documents (ADR 0116)."""

import asyncio
import importlib
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from azathoth.inputs import ContentRef, content_bytes_digest
from azathoth.providers import (
    BedrockConfiguration,
    BedrockLanguageModel,
    Boto3BedrockClient,
    ContentPart,
    NativeCitation,
    OpenRouterConfiguration,
    OpenRouterLanguageModel,
    Prompt,
    TextPart,
    UnsupportedModelRequestError,
    bedrock_content,
    giving_prompt_content,
)
from tests.providers.fake_bedrock import FakeBedrockClient

MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"

PDF = b"%PDF-1.7\n%%EOF\n"

DOCUMENT = ContentRef(
    digest=content_bytes_digest(PDF),
    media_type="application/pdf",
    size_bytes=len(PDF),
)

SHOWING = Prompt(
    parts=(TextPart(text="When was the claim received?"), ContentPart(content=DOCUMENT)),
    native_citations=True,
)


def reply(
    *content: dict[str, Any],
) -> dict[str, Any]:
    """Return a Converse reply whose message holds some content blocks."""

    return {
        "output": {"message": {"role": "assistant", "content": list(content)}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1290, "outputTokens": 40, "totalTokens": 1330},
        "metrics": {"latencyMs": 900},
    }


def cited(
    text: str,
    *citations: dict[str, Any],
) -> dict[str, Any]:
    """Return a block of generated text with the citations that support it."""

    return {"citationsContent": {"content": [{"text": text}], "citations": list(citations)}}


def citation(
    quote: str,
    location: dict[str, Any],
) -> dict[str, Any]:
    """Return one Converse citation of a quote at a location."""

    return {"title": "document-1", "sourceContent": [{"text": quote}], "location": location}


def page(
    start: int,
    end: int,
    document: int = 0,
) -> dict[str, Any]:
    """Return a citation location by pages."""

    return {"documentPage": {"documentIndex": document, "start": start, "end": end}}


def completed(
    raw: dict[str, Any],
) -> Any:
    """Return what a Bedrock model makes of one Converse reply to the prompt."""

    client = FakeBedrockClient(replies={MODEL: [raw]})

    with giving_prompt_content({DOCUMENT.digest: PDF}):
        return asyncio.run(BedrockLanguageModel(client, MODEL).complete(SHOWING))


def test_a_prompt_asking_for_native_citations_turns_them_on_for_each_document() -> None:
    with giving_prompt_content({DOCUMENT.digest: PDF}):
        blocks = bedrock_content(MODEL, SHOWING)

    assert blocks[1] == {
        "document": {
            "format": "pdf",
            "name": "document-1",
            "source": {"bytes": PDF},
            "citations": {"enabled": True},
        }
    }


def test_a_prompt_not_asking_turns_no_citations_on() -> None:
    with giving_prompt_content({DOCUMENT.digest: PDF}):
        blocks = bedrock_content(MODEL, SHOWING.model_copy(update={"native_citations": False}))

    document = blocks[1]["document"]

    assert isinstance(document, dict)
    assert "citations" not in document


def test_the_answer_joins_text_and_cited_text_in_order() -> None:
    response = completed(
        reply(
            {"text": "The claim was received "},
            cited("on December 14", citation("Received on December 14.", page(1, 1))),
            {"text": "."},
        )
    )

    assert response.text == "The claim was received on December 14."


def test_a_citation_by_pages_names_its_document_quote_pages_and_what_it_supports() -> None:
    response = completed(
        reply(cited("on December 14", citation("Received on December 14.", page(2, 3))))
    )

    assert response.citations == (
        NativeCitation(
            document=0,
            quote="Received on December 14.",
            pages=(2, 3),
            supports="on December 14",
        ),
    )


@pytest.mark.parametrize(
    "location",
    [
        pytest.param({"documentChar": {"documentIndex": 0, "start": 40, "end": 64}}, id="chars"),
        pytest.param({"documentChunk": {"documentIndex": 0, "start": 2, "end": 3}}, id="chunks"),
    ],
)
def test_a_citation_by_characters_or_chunks_names_no_pages(
    location: dict[str, Any],
) -> None:
    response = completed(reply(cited("December 14", citation("December 14", location))))

    (native,) = response.citations

    assert (native.document, native.pages) == (0, None)


def test_a_page_range_with_no_end_is_its_first_page() -> None:
    response = completed(
        reply(
            cited(
                "x",
                citation("Received.", {"documentPage": {"documentIndex": 0, "start": 4}}),
            )
        )
    )

    assert response.citations[0].pages == (4, 4)


def test_citations_of_no_document_or_with_no_quote_are_passed_over() -> None:
    response = completed(
        reply(
            cited(
                "x",
                citation("A web page.", {"web": {"url": "https://example.com", "domain": "e"}}),
                {"sourceContent": [], "location": page(1, 1)},
                {"sourceContent": [{"text": "kept"}]},
                citation("Received.", page(1, 1, document=1)),
            )
        )
    )

    assert [(native.document, native.quote) for native in response.citations] == [(1, "Received.")]


def test_several_passages_of_one_citation_are_one_quote() -> None:
    response = completed(
        reply(
            cited(
                "x",
                {
                    "sourceContent": [{"text": "Received on"}, {"text": "December 14."}],
                    "location": page(1, 1),
                },
            )
        )
    )

    assert response.citations[0].quote == "Received on December 14."


def test_an_empty_passage_adds_nothing_to_the_quote() -> None:
    response = completed(
        reply(
            cited(
                "x",
                {
                    "sourceContent": [{"text": ""}, {"text": "Received."}],
                    "location": page(1, 1),
                },
            )
        )
    )

    assert response.citations[0].quote == "Received."


def test_a_reply_without_citations_has_none() -> None:
    assert completed(reply({"text": "December 14."})).citations == ()


@pytest.mark.parametrize(
    "value",
    [
        pytest.param({"document": -1, "quote": "x"}, id="negative-document"),
        pytest.param({"document": 0, "quote": ""}, id="empty-quote"),
        pytest.param({"document": 0, "quote": "x", "page": 1}, id="extra-key"),
    ],
)
def test_a_native_citation_is_validated(
    value: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        NativeCitation.model_validate(value)


def test_a_prompt_names_native_citations_only_when_it_asks() -> None:
    assert SHOWING.model_dump(mode="json")["native_citations"] is True
    assert "native_citations" not in Prompt(text="x").model_dump(mode="json")


def test_openrouter_refuses_native_citations_before_it_sends_anything() -> None:
    sent: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500, request=request)

    model = OpenRouterLanguageModel(
        OpenRouterConfiguration(
            api_key=SecretStr("test-openrouter-key"),
            base_url="https://openrouter.test/api/v1",
            timeout_seconds=10.0,
        ),
        "anthropic/claude-sonnet-4",
        transport=httpx.MockTransport(handler),
    )

    with (
        giving_prompt_content({DOCUMENT.digest: PDF}),
        pytest.raises(UnsupportedModelRequestError) as raised,
    ):
        asyncio.run(model.complete(SHOWING))

    assert str(raised.value) == (
        "OpenRouter model 'anthropic/claude-sonnet-4' cannot return native citations; cite "
        "segments in the reply instead."
    )
    assert sent == []


@pytest.fixture
def boto3_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Boto3BedrockClient:
    """Return a client over boto3, with credentials that are never used."""

    pytest.importorskip("boto3")

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    return Boto3BedrockClient(
        BedrockConfiguration(region="eu-central-1", timeout_seconds=12.0, max_attempts=4)
    )


@pytest.fixture
def runtime(
    boto3_client: Boto3BedrockClient,
) -> Iterator[Any]:
    """Stub the client's bedrock-runtime calls."""

    stubber_type = importlib.import_module("botocore.stub").Stubber

    with stubber_type(boto3_client._runtime) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def test_a_cited_converse_call_has_the_shape_converse_defines_both_ways(
    boto3_client: Boto3BedrockClient,
    runtime: Any,
) -> None:
    #
    # botocore validates the request against Converse's service model, and
    # the stubbed reply against its output shape, so both are Converse's own.
    #
    with giving_prompt_content({DOCUMENT.digest: PDF}):
        content = bedrock_content(MODEL, SHOWING)

    runtime.add_response(
        "converse",
        reply(
            {"text": "It was received "},
            cited("on December 14", citation("Received on December 14.", page(1, 1))),
        ),
        {"modelId": MODEL, "messages": [{"role": "user", "content": content}]},
    )

    with giving_prompt_content({DOCUMENT.digest: PDF}):
        response = asyncio.run(BedrockLanguageModel(boto3_client, MODEL).complete(SHOWING))

    assert response.text == "It was received on December 14"
    assert response.citations == (
        NativeCitation(
            document=0,
            quote="Received on December 14.",
            pages=(1, 1),
            supports="on December 14",
        ),
    )
