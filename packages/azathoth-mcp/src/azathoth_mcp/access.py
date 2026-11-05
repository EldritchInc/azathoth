"""Who is calling, and what they may call (ADR 0111).

A caller over stdio started the server with its own credentials, and may
call everything the server offers. A caller over HTTP holds a token, and may
call only what the token's scopes allow:

- `azathoth:invoke:<tool>` for each exposed workflow's tool;
- `azathoth:read` for `get_invocation`, which then returns only the
  invocations recorded with the caller's own subject;
- `azathoth:read:all` to read every invocation of an exposed workflow.

The caller is recorded with every invocation, under `mcp` in its caller
metadata, so `invocation show` names who made it.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

SCOPE_PREFIX = "azathoth:"

READ_SCOPE = "azathoth:read"
"""Read the invocations recorded with the caller's own subject."""

READ_ALL_SCOPE = "azathoth:read:all"
"""Read every invocation of an exposed workflow, whoever made it."""

CALLER_METADATA_KEY = "mcp"
"""Where an invocation's caller metadata records the MCP caller."""


def invoke_scope(
    tool: str,
) -> str:
    """Return the scope that allows calling one exposed workflow's tool."""

    return f"azathoth:invoke:{tool}"


class Transport(StrEnum):
    """How a caller reaches the server."""

    STDIO = "stdio"
    HTTP = "http"


class ToolAccessError(PermissionError):
    """Raised when a caller's token does not allow a call."""


class McpCaller(BaseModel):
    """The client one call comes from.

    `scopes` is what the caller's token grants, or `None` for a caller the
    server does not authorize, over stdio or a loopback-only HTTP server.
    `subject` and `client_id` come from the token, when there is one.
    """

    model_config = ConfigDict(frozen=True)

    transport: Transport
    subject: str | None = Field(default=None, min_length=1)
    client_id: str | None = Field(default=None, min_length=1)
    scopes: frozenset[str] | None = None

    def require(
        self,
        scope: str,
    ) -> None:
        """Refuse a call this caller's token does not allow.

        Raises:
            ToolAccessError: The caller is authorized, and its token does not
                carry the scope.
        """

        if self.scopes is not None and scope not in self.scopes:
            raise ToolAccessError(f'This call needs the scope "{scope}".')

    @property
    def reads_every_invocation(
        self,
    ) -> bool:
        """Report whether this caller may read invocations other callers made."""

        return self.scopes is None or READ_ALL_SCOPE in self.scopes

    def may_read(
        self,
        caller_metadata: dict[str, JsonValue],
    ) -> bool:
        """Report whether this caller may read an invocation with this caller metadata.

        A caller that reads every invocation may read any. Another may read
        only one recorded over MCP with its own subject.
        """

        if self.reads_every_invocation:
            return True

        recorded = caller_metadata.get(CALLER_METADATA_KEY)

        return (
            self.subject is not None
            and isinstance(recorded, dict)
            and recorded.get("subject") == self.subject
        )

    def caller_metadata(
        self,
        tool: str,
    ) -> dict[str, JsonValue]:
        """Return the caller metadata one invocation of a tool records.

        It holds the transport and the tool, and the token's subject and
        client ID when there is a token. It never holds the token itself.
        """

        recorded: dict[str, JsonValue] = {
            "transport": self.transport.value,
            "tool": tool,
        }

        if self.subject is not None:
            recorded["subject"] = self.subject

        if self.client_id is not None:
            recorded["client_id"] = self.client_id

        return {CALLER_METADATA_KEY: recorded}


STDIO_CALLER = McpCaller(transport=Transport.STDIO)
"""The one caller of a server over stdio."""


__all__ = [
    "CALLER_METADATA_KEY",
    "READ_ALL_SCOPE",
    "READ_SCOPE",
    "SCOPE_PREFIX",
    "STDIO_CALLER",
    "McpCaller",
    "ToolAccessError",
    "Transport",
    "invoke_scope",
]
