"""Remote command-line parser construction (ADR 0124)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction

REMOTE_COMMAND = "remote"

REMOTE_ACTION_ATTRIBUTE = "remote_action"

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
