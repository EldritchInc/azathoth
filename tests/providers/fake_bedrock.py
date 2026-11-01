"""A fake `BedrockClient`, so Bedrock is tested with no network and no account."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from azathoth.providers import BedrockClientError


@dataclass
class FakeBedrockClient:
    """Answer Bedrock's calls from what a test gives it, and record each call.

    `inference_profile_pages` holds one list of profiles per page; every page
    but the last carries a `nextToken` naming the next. `replies` holds, per
    model ID, the Converse replies or errors to give, in order.
    """

    foundation_models: list[dict[str, object]] = field(default_factory=list)
    inference_profile_pages: list[list[dict[str, object]]] = field(
        default_factory=lambda: [[]],
    )
    replies: dict[str, list[Mapping[str, object] | BedrockClientError]] = field(
        default_factory=dict,
    )
    listing_error: BedrockClientError | None = None
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def converse(
        self,
        model_id: str,
        text: str,
    ) -> Mapping[str, object]:
        self.calls.append(("converse", model_id, text))

        reply = self.replies[model_id].pop(0)

        if isinstance(reply, BedrockClientError):
            raise reply

        return reply

    def list_foundation_models(
        self,
    ) -> Mapping[str, object]:
        self.calls.append(("list_foundation_models",))

        if self.listing_error is not None:
            raise self.listing_error

        return {"modelSummaries": list(self.foundation_models)}

    def list_inference_profiles(
        self,
        next_token: str | None = None,
    ) -> Mapping[str, object]:
        self.calls.append(("list_inference_profiles", next_token or ""))

        if self.listing_error is not None:
            raise self.listing_error

        index = 0 if next_token is None else int(next_token.removeprefix("page-"))
        page: dict[str, object] = {
            "inferenceProfileSummaries": list(self.inference_profile_pages[index]),
        }

        if index + 1 < len(self.inference_profile_pages):
            page["nextToken"] = f"page-{index + 1}"

        return page
