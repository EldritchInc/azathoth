"""Remote command-line parser construction (ADR 0124, ADR 0126)."""

from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from uuid import UUID

from azathoth.remote import DEFAULT_HOST, DEFAULT_PORT, REMOTE_TOKEN_VARIABLE

REMOTE_COMMAND = "remote"

REMOTE_ACTION_ATTRIBUTE = "remote_action"

REMOTE_SERVE_ACTION = "serve"

REMOTE_HOST_ATTRIBUTE = "remote_host"

REMOTE_PORT_ATTRIBUTE = "remote_port"

REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE = "remote_accept_restricted"

REMOTE_PUSH_ACTION = "push"

REMOTE_PULL_ACTION = "pull"

REMOTE_TARGET_ATTRIBUTE = "remote_target"

REMOTE_ADD_ACTION = "add"
REMOTE_LIST_ACTION = "list"
REMOTE_REMOVE_ACTION = "remove"

REMOTE_NAME_ATTRIBUTE = "remote_name"

REMOTE_URL_ATTRIBUTE = "remote_url"

REMOTE_TOKEN_VARIABLE_ATTRIBUTE = "remote_token_variable"

REMOTE_WORKFLOWS_ATTRIBUTE = "remote_workflows"

REMOTE_TOOLS_ATTRIBUTE = "remote_tools"

REMOTE_BENCHMARKS_ATTRIBUTE = "remote_benchmarks"

REMOTE_INCLUDE_RESTRICTED_ATTRIBUTE = "remote_include_restricted"

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
        help=(
            "Name the remotes this instance reaches, push to and pull from them, or serve "
            "this instance as one."
        ),
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

    for action, verb, help_text in (
        (REMOTE_PUSH_ACTION, "push", "Push documents, with what they need, to a remote."),
        (REMOTE_PULL_ACTION, "pull", "Pull documents, with what they need, from a remote."),
    ):
        sync_parser = remote_actions.add_parser(action, help=help_text)

        sync_parser.add_argument(
            REMOTE_TARGET_ATTRIBUTE,
            metavar="REMOTE",
            help=(
                "A remote's name, its token read from the variable it was named with, or its "
                f"URL, its token read from {REMOTE_TOKEN_VARIABLE}."
            ),
        )

        sync_parser.add_argument(
            "--workflow",
            dest=REMOTE_WORKFLOWS_ATTRIBUTE,
            metavar="WORKFLOW_ID",
            type=UUID,
            action="append",
            default=[],
            help=f"A workflow to {verb}; give it again for more.",
        )

        sync_parser.add_argument(
            "--tool",
            dest=REMOTE_TOOLS_ATTRIBUTE,
            metavar="TOOL_ID@VERSION",
            action="append",
            default=[],
            help=f"A tool version to {verb}; give it again for more.",
        )

        sync_parser.add_argument(
            "--benchmark",
            dest=REMOTE_BENCHMARKS_ATTRIBUTE,
            metavar="BENCHMARK_ID",
            type=UUID,
            action="append",
            default=[],
            help=f"A benchmark to {verb}; give it again for more.",
        )

        if action == REMOTE_PULL_ACTION:
            sync_parser.add_argument(
                "--include-restricted",
                dest=REMOTE_INCLUDE_RESTRICTED_ATTRIBUTE,
                action="store_true",
                help="Pull restricted benchmarks too, which are otherwise withheld.",
            )

    add_parser = remote_actions.add_parser(
        REMOTE_ADD_ACTION,
        help="Name a remote, so commands can name it instead of its URL.",
    )

    add_parser.add_argument(
        REMOTE_NAME_ATTRIBUTE,
        metavar="NAME",
        help="A name for the remote: letters, digits, '_' or '-'.",
    )

    add_parser.add_argument(
        REMOTE_URL_ATTRIBUTE,
        metavar="URL",
        help="The remote's http or https URL.",
    )

    add_parser.add_argument(
        "--token-variable",
        dest=REMOTE_TOKEN_VARIABLE_ATTRIBUTE,
        metavar="VARIABLE",
        default=REMOTE_TOKEN_VARIABLE,
        help=(
            f"The environment variable its token is read from; {REMOTE_TOKEN_VARIABLE} by "
            "default. Only the variable's name is kept, never a token."
        ),
    )

    remote_actions.add_parser(
        REMOTE_LIST_ACTION,
        help="List the remotes this instance names, by name.",
    )

    remove_parser = remote_actions.add_parser(
        REMOTE_REMOVE_ACTION,
        help="Forget a remote's name; nothing at the remote changes.",
    )

    remove_parser.add_argument(
        REMOTE_NAME_ATTRIBUTE,
        metavar="NAME",
        help="The name to forget.",
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
