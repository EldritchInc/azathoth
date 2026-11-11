"""Remote command-line parser construction (ADR 0124)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

from azathoth.remote import DEFAULT_HOST, DEFAULT_PORT

REMOTE_COMMAND = "remote"

REMOTE_ACTION_ATTRIBUTE = "remote_action"

REMOTE_SERVE_ACTION = "serve"

REMOTE_HOST_ATTRIBUTE = "remote_host"

REMOTE_PORT_ATTRIBUTE = "remote_port"

REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE = "remote_accept_restricted"

REMOTE_TOKEN_ACTION = "token"

REMOTE_TOKEN_ACTION_ATTRIBUTE = "remote_token_action"

REMOTE_TOKEN_CREATE_ACTION = "create"
REMOTE_TOKEN_LIST_ACTION = "list"
REMOTE_TOKEN_REVOKE_ACTION = "revoke"

REMOTE_TOKEN_NAME_ATTRIBUTE = "remote_token_name"

REMOTE_TOKEN_ALL_ATTRIBUTE = "remote_token_all"


def add_remote_parser(
    commands: _SubParsersAction[ArgumentParser],
) -> None:
    """Add the remote commands to the Azathoth parser."""

    remote_parser = commands.add_parser(
        REMOTE_COMMAND,
        help="Serve this instance as a remote, and issue the tokens that reach it.",
    )

    remote_actions = remote_parser.add_subparsers(
        dest=REMOTE_ACTION_ATTRIBUTE,
    )

    serve_parser = remote_actions.add_parser(
        REMOTE_SERVE_ACTION,
        help="Serve this instance's workflows, tools and benchmarks to push to and pull from.",
    )

    serve_parser.add_argument(
        "--host",
        dest=REMOTE_HOST_ATTRIBUTE,
        default=DEFAULT_HOST,
        help=f"The address to listen on; {DEFAULT_HOST}, this machine only, by default.",
    )

    serve_parser.add_argument(
        "--port",
        dest=REMOTE_PORT_ATTRIBUTE,
        type=int,
        default=DEFAULT_PORT,
        help=f"The port to listen on; {DEFAULT_PORT} by default.",
    )

    serve_parser.add_argument(
        "--accept-restricted",
        dest=REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE,
        action="store_true",
        help="Receive restricted data; declare it only for a remote that may hold it.",
    )

    token_parser = remote_actions.add_parser(
        REMOTE_TOKEN_ACTION,
        help="Create, list and revoke the bearer tokens that reach this remote.",
    )

    token_actions = token_parser.add_subparsers(
        dest=REMOTE_TOKEN_ACTION_ATTRIBUTE,
    )

    token_create_parser = token_actions.add_parser(
        REMOTE_TOKEN_CREATE_ACTION,
        help="Create a token, and show it once.",
    )

    token_create_parser.add_argument(
        REMOTE_TOKEN_NAME_ATTRIBUTE,
        metavar="NAME",
        help="A name for the token: letters, digits, '.', '_' or '-'.",
    )

    token_list_parser = token_actions.add_parser(
        REMOTE_TOKEN_LIST_ACTION,
        help="List the active tokens, oldest first.",
    )

    token_list_parser.add_argument(
        "--all",
        dest=REMOTE_TOKEN_ALL_ATTRIBUTE,
        action="store_true",
        help="List revoked tokens too.",
    )

    token_revoke_parser = token_actions.add_parser(
        REMOTE_TOKEN_REVOKE_ACTION,
        help="Revoke the active token of a name.",
    )

    token_revoke_parser.add_argument(
        REMOTE_TOKEN_NAME_ATTRIBUTE,
        metavar="NAME",
        help="The name of the token to revoke.",
    )
