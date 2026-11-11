"""What a remote and its client agree on before anything travels (ADR 0124)."""

from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

PROTOCOL_VERSION: Final = 1
"""The version of the remote protocol this Azathoth speaks."""

DEFAULT_EDITION: Final = "community"
"""The edition a remote names when no plugin names another."""

MAX_PUSH_BYTES: Final = 64 * 1024 * 1024
"""The largest push bundle a remote accepts, in bytes."""

MAX_CONTENT_BYTES: Final = 10 * 1024 * 1024
"""The largest content blob a push carries or a pull fetches, in bytes."""

DEFAULT_HOST: Final = "127.0.0.1"
"""Where `azathoth remote serve` listens unless told otherwise: this machine only."""

DEFAULT_PORT: Final = 8470
"""The port `azathoth remote serve` listens on unless told otherwise."""

MISSING_REMOTE_EXTRA_MESSAGE: Final = (
    "azathoth remote serve needs starlette and uvicorn, which are not installed; install "
    "azathoth-ai[remote]."
)
"""What `azathoth remote serve` without the `remote` extra reports."""


class ProtocolMismatchError(ValueError):
    """The other side of a remote exchange speaks another protocol version."""


def require_protocol(
    protocol: int,
    *,
    peer: str = "The remote",
) -> None:
    """Refuse a protocol version other than this Azathoth's, naming both.

    `peer` names the other side as the message begins: the remote, to a
    client, or the client, to a remote.

    Raises:
        ProtocolMismatchError: The versions differ.
    """

    if protocol != PROTOCOL_VERSION:
        raise ProtocolMismatchError(
            f"{peer} speaks remote protocol {protocol}, and this Azathoth speaks remote "
            f"protocol {PROTOCOL_VERSION}; run versions of Azathoth that speak the same "
            "protocol on both."
        )


class Capabilities(BaseModel):
    """What a remote tells a client about itself, before the client sends anything.

    `plugins` names the plugin serving each seam that a plugin serves, by
    seam. `accepts_restricted` is true only for a remote started to receive
    restricted data (ADR 0123).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    protocol: int = Field(
        ge=1,
    )

    azathoth_version: str = Field(
        min_length=1,
    )

    schema_version: int = Field(
        ge=1,
    )

    edition: str = Field(
        default=DEFAULT_EDITION,
        min_length=1,
    )

    plugins: dict[str, str] = Field(
        default_factory=dict,
    )

    accepts_restricted: bool = False

    def require_protocol(
        self,
    ) -> "Capabilities":
        """Return these capabilities, or refuse them when the remote speaks another protocol.

        Raises:
            ProtocolMismatchError: The remote's protocol is not this Azathoth's.
        """

        require_protocol(self.protocol)

        return self


__all__ = [
    "DEFAULT_EDITION",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "MAX_CONTENT_BYTES",
    "MAX_PUSH_BYTES",
    "MISSING_REMOTE_EXTRA_MESSAGE",
    "PROTOCOL_VERSION",
    "Capabilities",
    "ProtocolMismatchError",
    "require_protocol",
]
