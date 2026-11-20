"""Write the tool document of a tool an MCP server serves (ADRs 0119 and 0133).

`azathoth tool from-mcp` asks the service API's `tools.from_mcp` for the
document of the tool named, its implementation pinned to the schemas the
server serves now, and prints it. Nothing is stored: the operator reads the
document and imports it as any other.
"""

import sys

from azathoth import api
from azathoth.api.mcp_tools import LISTING_TIMEOUT_SECONDS
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.service import service_instance
from azathoth.tools.mcp_execution import McpConnector

SERVER_NAMED_TWICE_MESSAGE = "Name the MCP server with --url or with a command after --, not both."

SERVER_NOT_NAMED_MESSAGE = "Name the MCP server with --url, or with a command after --."


def tool_from_mcp(
    *,
    tool: str,
    url: str | None = None,
    command: tuple[str, ...] = (),
    authorization: str | None = None,
    grants: tuple[str, ...] = (),
    timeout_seconds: float | None = None,
    connect: McpConnector | None = None,
) -> int:
    """Print the tool document of one tool an MCP server serves, pinned as it is served now.

    The implementation keeps the timeout named, if any; listing the tools is
    given that timeout, or 30 seconds. The server is named with the
    command's own options, so naming it twice or not at all is said in
    their terms.
    """

    if url is not None and command:
        print(SERVER_NAMED_TWICE_MESSAGE, file=sys.stderr)

        return 1

    if url is None and not command:
        print(SERVER_NOT_NAMED_MESSAGE, file=sys.stderr)

        return 1

    configuration = CliRuntimeConfiguration.from_environment()

    try:
        exported = service_instance(configuration).tools.from_mcp(
            tool,
            url=url,
            command=command,
            authorization=authorization,
            grants=grants,
            timeout_seconds=timeout_seconds,
            connect=connect,
        )
    except api.ApiError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    sys.stdout.write(exported.text)

    return 0


__all__ = [
    "LISTING_TIMEOUT_SECONDS",
    "SERVER_NAMED_TWICE_MESSAGE",
    "SERVER_NOT_NAMED_MESSAGE",
    "tool_from_mcp",
]
