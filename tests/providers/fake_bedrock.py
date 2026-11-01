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


def foundation_model(
    model_id: str,
    *,
    name: str | None = None,
    inputs: tuple[str, ...] = ("TEXT",),
    outputs: tuple[str, ...] = ("TEXT",),
    inference_types: tuple[str, ...] = ("ON_DEMAND",),
    streaming: bool = True,
    status: str = "ACTIVE",
) -> dict[str, object]:
    """Return one foundation model summary, as `ListFoundationModels` gives it."""

    return {
        "modelArn": f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
        "modelId": model_id,
        "modelName": name or model_id,
        "providerName": model_id.split(".")[0],
        "inputModalities": list(inputs),
        "outputModalities": list(outputs),
        "responseStreamingSupported": streaming,
        "customizationsSupported": [],
        "inferenceTypesSupported": list(inference_types),
        "modelLifecycle": {"status": status},
    }


def inference_profile(
    profile_id: str,
    *model_ids: str,
    name: str | None = None,
    status: str = "ACTIVE",
    profile_type: str = "SYSTEM_DEFINED",
) -> dict[str, object]:
    """Return one inference profile summary, as `ListInferenceProfiles` gives it."""

    return {
        "inferenceProfileName": name or profile_id,
        "inferenceProfileArn": (
            f"arn:aws:bedrock:us-east-1:123456789012:inference-profile/{profile_id}"
        ),
        "inferenceProfileId": profile_id,
        "models": [
            {"modelArn": f"arn:aws:bedrock:{region}::foundation-model/{model_id}"}
            for model_id in model_ids
            for region in ("us-east-1", "us-west-2")
        ],
        "status": status,
        "type": profile_type,
    }
