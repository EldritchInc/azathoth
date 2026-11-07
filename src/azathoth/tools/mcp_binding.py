"""The binding of a tool implementation to a tool an MCP server serves (ADR 0119).

An MCP implementation runs no source of its own. It names a server, by the
command that starts a stdio server or the URL of an HTTP one, the remote
tool it calls, the digest of that tool's schemas when it was pinned, and the
credentials the call needs. The binding is part of the implementation, so
its digest covers exactly what is called.
"""

import hashlib
import json
import re
import shlex
from typing import Any, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

MCP_TOOL_RUNTIME = "mcp"
"""The runtime name of tool implementations that call a tool an MCP server serves."""

MCP_SCHEMA_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
"""A pinned schema digest is a sha256 digest in lowercase hex."""

MCP_URL_SCHEMES = ("http", "https")
"""The schemes an MCP server reached over HTTP may be named by."""

ENVIRONMENT_VARIABLE_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
"""An authorization variable is named exactly: letters, digits and underscores."""

_SCHEMA_DIGEST = re.compile(MCP_SCHEMA_DIGEST_PATTERN)

_VARIABLE_NAME = re.compile(ENVIRONMENT_VARIABLE_NAME_PATTERN)


def mcp_schema_digest(
    input_schema: JsonValue,
    output_schema: JsonValue | None,
) -> str:
    """Return the digest of a remote tool's schemas, as a binding pins it.

    The digest is the sha256 of the canonical JSON of the tool's
    `inputSchema` and `outputSchema`, with sorted keys and no insignificant
    whitespace; a tool that names no output schema is digested with null.
    """

    canonical = json.dumps(
        {"inputSchema": input_schema, "outputSchema": output_schema},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class McpServer(BaseModel):
    """Where an MCP tool is served: the command of a stdio server, or the URL of an HTTP one."""

    model_config = ConfigDict(frozen=True)

    command: tuple[str, ...] | None = Field(default=None, min_length=1)
    url: str | None = None

    @model_validator(mode="after")
    def validate_one_transport(self) -> Self:
        """Require exactly one of a command or a URL, each well formed.

        Raises:
            ValueError: Both or neither is named, a command argument is
                empty, or the URL is not an http or https URL.
        """

        if (self.command is None) == (self.url is None):
            raise ValueError("An MCP server is named by exactly one of a command or a URL.")

        if self.command is not None and any(not argument for argument in self.command):
            raise ValueError("MCP server command arguments cannot be empty.")

        if self.url is not None:
            parts = urlsplit(self.url)

            if parts.scheme not in MCP_URL_SCHEMES or not parts.netloc:
                raise ValueError(f"MCP server URL {self.url!r} must be an http or https URL.")

        return self

    @property
    def is_stdio(self) -> bool:
        """Return whether the server is started as a process speaking over stdio."""

        return self.command is not None

    def describe(
        self,
    ) -> str:
        """Return the server as an operator names it: its command, or its URL."""

        if self.command is not None:
            return shlex.join(self.command)

        return str(self.url)

    @model_serializer(mode="wrap")
    def serialize_its_transport(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the server, naming only the transport it uses."""

        serialized: dict[str, Any] = handler(self)

        return {name: value for name, value in serialized.items() if value is not None}


class McpCredentials(BaseModel):
    """The credentials one call of an MCP tool needs, named and never held.

    An HTTP server's `authorization` names the environment variable whose
    value is sent as a bearer token. A stdio server's credentials are the
    environment variables its implementation grants the process.
    """

    model_config = ConfigDict(frozen=True)

    authorization: str | None = None

    @field_validator("authorization")
    @classmethod
    def validate_variable_name(
        cls,
        authorization: str | None,
    ) -> str | None:
        """Require the authorization variable to be named exactly.

        Raises:
            ValueError: The name is not a variable name.
        """

        if authorization is not None and _VARIABLE_NAME.fullmatch(authorization) is None:
            raise ValueError(
                f"Authorization variable {authorization!r} must be a variable name of "
                "letters, digits and underscores."
            )

        return authorization

    @model_serializer(mode="wrap")
    def serialize_what_is_named(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the credentials, omitting what is not named."""

        serialized: dict[str, Any] = handler(self)

        return {name: value for name, value in serialized.items() if value is not None}


class McpToolBinding(BaseModel):
    """One remote tool an MCP implementation calls, pinned to its schemas (ADR 0119)."""

    model_config = ConfigDict(frozen=True)

    server: McpServer
    tool: str = Field(min_length=1)
    schema_digest: str
    credentials: McpCredentials = Field(default_factory=McpCredentials)

    @field_validator("schema_digest")
    @classmethod
    def validate_schema_digest(
        cls,
        schema_digest: str,
    ) -> str:
        """Require a sha256 digest in lowercase hex.

        Raises:
            ValueError: The digest is not 64 lowercase hex characters.
        """

        if _SCHEMA_DIGEST.fullmatch(schema_digest) is None:
            raise ValueError(
                "An MCP tool's schema digest must be a sha256 digest of 64 lowercase hex "
                "characters."
            )

        return schema_digest

    @model_validator(mode="after")
    def validate_authorization_transport(self) -> Self:
        """Require an authorization variable only of a server reached over HTTP.

        Raises:
            ValueError: A stdio server names an authorization variable.
        """

        if self.credentials.authorization is not None and self.server.is_stdio:
            raise ValueError(
                "Only an MCP server reached over HTTP takes an authorization variable; a "
                "stdio server is given its credentials as environment grants."
            )

        return self

    @model_serializer(mode="wrap")
    def serialize_without_empty_credentials(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        """Serialize the binding, omitting credentials that name nothing."""

        serialized: dict[str, Any] = handler(self)

        if not serialized.get("credentials"):
            serialized.pop("credentials", None)

        return serialized


__all__ = [
    "ENVIRONMENT_VARIABLE_NAME_PATTERN",
    "MCP_SCHEMA_DIGEST_PATTERN",
    "MCP_TOOL_RUNTIME",
    "MCP_URL_SCHEMES",
    "McpCredentials",
    "McpServer",
    "McpToolBinding",
    "mcp_schema_digest",
]
