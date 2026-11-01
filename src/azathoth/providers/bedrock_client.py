"""The three Bedrock calls Azathoth makes, behind one small protocol (ADR 0103).

Everything else in Azathoth reaches Bedrock through `BedrockClient`, so its
tests run against a fake client, and nothing but this module imports boto3.
boto3 is imported only when Bedrock is turned on.
"""

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from azathoth.providers.bedrock_configuration import (
    BEDROCK_PRICING_VARIABLE,
    MISSING_REGION_MESSAGE,
    BedrockConfiguration,
    BedrockConfigurationError,
    BedrockPricing,
    BedrockUnavailableError,
    bedrock_enabled,
    load_bedrock_pricing,
)

INFERENCE_PROFILE_TYPE = "SYSTEM_DEFINED"
"""The inference profiles Azathoth lists: those AWS defines."""

AWS_REGION_VARIABLE = "AWS_REGION"
"""AWS's variable naming the region, which ECS and Lambda set."""

AWS_DEFAULT_REGION_VARIABLE = "AWS_DEFAULT_REGION"
"""AWS's older variable naming the region."""


class BedrockClientError(Exception):
    """A Bedrock call failed, after botocore's own retries.

    `code` is AWS's error code, such as `ThrottlingException`, or, for a
    failure before AWS answered, the name of botocore's error, such as
    `NoCredentialsError`.
    """

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class BedrockClient(Protocol):
    """The Bedrock calls Azathoth makes, each returning AWS's reply as it is."""

    def converse(
        self,
        model_id: str,
        text: str,
    ) -> Mapping[str, object]:
        """Send one user message to one model, through Converse.

        Raises:
            BedrockClientError: The call failed.
        """

        ...

    def list_foundation_models(
        self,
    ) -> Mapping[str, object]:
        """Return the region's foundation models.

        Raises:
            BedrockClientError: The call failed.
        """

        ...

    def list_inference_profiles(
        self,
        next_token: str | None = None,
    ) -> Mapping[str, object]:
        """Return one page of the region's system-defined inference profiles.

        Raises:
            BedrockClientError: The call failed.
        """

        ...


@dataclass(frozen=True)
class BedrockDriver:
    """How Azathoth finds AWS's region and makes Bedrock clients.

    `boto3_driver` returns boto3's; tests pass their own.
    """

    region: Callable[[], str | None]
    client: Callable[[BedrockConfiguration], BedrockClient]


class Boto3BedrockClient:
    """A `BedrockClient` over boto3, using AWS's own credential chain."""

    def __init__(
        self,
        configuration: BedrockConfiguration,
    ) -> None:
        boto3 = _import("boto3")
        botocore_config = _import("botocore.config")
        botocore_exceptions = _import("botocore.exceptions")

        config = botocore_config.Config(
            connect_timeout=configuration.timeout_seconds,
            read_timeout=configuration.timeout_seconds,
            retries={
                "mode": "standard",
                "total_max_attempts": configuration.max_attempts,
            },
        )

        session = boto3.session.Session(region_name=configuration.region)

        self._control: Any = session.client("bedrock", config=config)
        self._runtime: Any = session.client("bedrock-runtime", config=config)
        self._client_error: type[Exception] = botocore_exceptions.ClientError
        self._botocore_error: type[Exception] = botocore_exceptions.BotoCoreError

    def converse(
        self,
        model_id: str,
        text: str,
    ) -> Mapping[str, object]:
        return self._call(
            self._runtime.converse,
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": text}],
                },
            ],
        )

    def list_foundation_models(
        self,
    ) -> Mapping[str, object]:
        return self._call(self._control.list_foundation_models)

    def list_inference_profiles(
        self,
        next_token: str | None = None,
    ) -> Mapping[str, object]:
        if next_token is None:
            return self._call(
                self._control.list_inference_profiles,
                typeEquals=INFERENCE_PROFILE_TYPE,
            )

        return self._call(
            self._control.list_inference_profiles,
            typeEquals=INFERENCE_PROFILE_TYPE,
            nextToken=next_token,
        )

    def _call(
        self,
        operation: Callable[..., Any],
        **parameters: object,
    ) -> Mapping[str, object]:
        """Make one call, turning botocore's errors into `BedrockClientError`."""

        try:
            reply = operation(**parameters)
        except self._client_error as exc:
            error = getattr(exc, "response", {}).get("Error", {})

            raise BedrockClientError(
                str(error.get("Code") or type(exc).__name__),
                str(error.get("Message") or ""),
            ) from exc
        except self._botocore_error as exc:
            raise BedrockClientError(type(exc).__name__, str(exc)) from exc

        if not isinstance(reply, Mapping):
            raise BedrockClientError("InvalidResponse", "Bedrock returned no reply.")

        return reply


def boto3_driver() -> BedrockDriver:
    """Return the driver that finds the region, and makes clients, through boto3.

    Raises:
        BedrockUnavailableError: The `bedrock` extra is not installed.
    """

    boto3 = _import("boto3")

    def region() -> str | None:
        name = boto3.session.Session().region_name

        return str(name) if name else None

    return BedrockDriver(region=region, client=Boto3BedrockClient)


def configure_bedrock(
    environ: Mapping[str, str],
    *,
    driver: BedrockDriver | None = None,
) -> BedrockConfiguration | None:
    """Return the Bedrock configuration the environment asks for, or None when it is off.

    The region is AWS's own: `AWS_REGION`, then `AWS_DEFAULT_REGION`, then
    the region of the AWS profile. Prices come from the document `AZATHOTH_BEDROCK_PRICING` names.

    Raises:
        BedrockUnavailableError: Bedrock is on, but the `bedrock` extra is not
            installed.
        BedrockConfigurationError: No region is configured, or the pricing
            document cannot be used.
    """

    if not bedrock_enabled(environ):
        return None

    resolved = driver if driver is not None else boto3_driver()

    region = (
        _setting(environ, AWS_REGION_VARIABLE)
        or _setting(environ, AWS_DEFAULT_REGION_VARIABLE)
        or resolved.region()
    )

    if not region:
        raise BedrockConfigurationError(MISSING_REGION_MESSAGE)

    pricing_path = environ.get(BEDROCK_PRICING_VARIABLE, "").strip()

    pricing = load_bedrock_pricing(Path(pricing_path)) if pricing_path else BedrockPricing()

    return BedrockConfiguration(region=region, pricing=pricing)


def _setting(
    environ: Mapping[str, str],
    name: str,
) -> str | None:
    """Return one variable's value, or None when it is unset or blank."""

    value = environ.get(name, "").strip()

    return value or None


def _import(
    name: str,
) -> Any:
    """Import one boto3 module, or say which extra to install."""

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise BedrockUnavailableError() from exc


__all__ = [
    "AWS_DEFAULT_REGION_VARIABLE",
    "AWS_REGION_VARIABLE",
    "INFERENCE_PROFILE_TYPE",
    "BedrockClient",
    "BedrockClientError",
    "BedrockDriver",
    "Boto3BedrockClient",
    "boto3_driver",
    "configure_bedrock",
]
