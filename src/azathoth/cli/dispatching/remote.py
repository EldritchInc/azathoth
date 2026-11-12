"""Remote command dispatch for the Azathoth CLI (ADR 0124, ADR 0126)."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast
from uuid import UUID

from azathoth.cli.output_format import StatusOutputFormat
from azathoth.cli.parsing import (
    REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE,
    REMOTE_ACTION_ATTRIBUTE,
    REMOTE_ADD_ACTION,
    REMOTE_BENCHMARKS_ATTRIBUTE,
    REMOTE_HOST_ATTRIBUTE,
    REMOTE_INCLUDE_RESTRICTED_ATTRIBUTE,
    REMOTE_LIST_ACTION,
    REMOTE_NAME_ATTRIBUTE,
    REMOTE_OUTPUT_ATTRIBUTE,
    REMOTE_PORT_ATTRIBUTE,
    REMOTE_PULL_ACTION,
    REMOTE_PUSH_ACTION,
    REMOTE_REMOVE_ACTION,
    REMOTE_SERVE_ACTION,
    REMOTE_STATUS_ACTION,
    REMOTE_TARGET_ATTRIBUTE,
    REMOTE_TOKEN_ACTION,
    REMOTE_TOKEN_ACTION_ATTRIBUTE,
    REMOTE_TOKEN_ALL_ATTRIBUTE,
    REMOTE_TOKEN_CREATE_ACTION,
    REMOTE_TOKEN_LIST_ACTION,
    REMOTE_TOKEN_NAME_ATTRIBUTE,
    REMOTE_TOKEN_REVOKE_ACTION,
    REMOTE_TOKEN_VARIABLE_ATTRIBUTE,
    REMOTE_TOOLS_ATTRIBUTE,
    REMOTE_URL_ATTRIBUTE,
    REMOTE_WORKFLOWS_ATTRIBUTE,
)

RemoteTokenNameHandler = Callable[[str], int]
RemoteTokenListHandler = Callable[..., int]
RemoteServeHandler = Callable[..., int]
RemoteSyncHandler = Callable[..., int]
RemoteAddHandler = Callable[..., int]
RemoteListHandler = Callable[[], int]
RemoteNameHandler = Callable[[str], int]


def dispatch_remote_command(
    arguments: Namespace,
    *,
    create_remote_token: RemoteTokenNameHandler,
    list_remote_tokens: RemoteTokenListHandler,
    revoke_remote_token: RemoteTokenNameHandler,
    serve_remote: RemoteServeHandler,
    push_to_remote: RemoteSyncHandler,
    pull_from_remote: RemoteSyncHandler,
    add_remote: RemoteAddHandler,
    list_remotes: RemoteListHandler,
    remove_remote: RemoteNameHandler,
    remote_status: RemoteSyncHandler,
) -> int | None:
    """Dispatch one parsed remote command, or return None for one not given in full."""

    action = cast(str | None, getattr(arguments, REMOTE_ACTION_ATTRIBUTE, None))

    if action == REMOTE_SERVE_ACTION:
        return serve_remote(
            host=cast(str, getattr(arguments, REMOTE_HOST_ATTRIBUTE)),
            port=cast(int, getattr(arguments, REMOTE_PORT_ATTRIBUTE)),
            accept_restricted=cast(bool, getattr(arguments, REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE)),
        )

    if action in (REMOTE_PUSH_ACTION, REMOTE_PULL_ACTION, REMOTE_STATUS_ACTION):
        named = {
            "remote": cast(str, getattr(arguments, REMOTE_TARGET_ATTRIBUTE)),
            "workflows": cast(list[UUID], getattr(arguments, REMOTE_WORKFLOWS_ATTRIBUTE)),
            "tools": cast(list[str], getattr(arguments, REMOTE_TOOLS_ATTRIBUTE)),
            "benchmarks": cast(list[UUID], getattr(arguments, REMOTE_BENCHMARKS_ATTRIBUTE)),
        }

        if action == REMOTE_PUSH_ACTION:
            return push_to_remote(**named)

        if action == REMOTE_STATUS_ACTION:
            return remote_status(
                **named,
                output=StatusOutputFormat(cast(str, getattr(arguments, REMOTE_OUTPUT_ATTRIBUTE))),
            )

        return pull_from_remote(
            **named,
            include_restricted=cast(bool, getattr(arguments, REMOTE_INCLUDE_RESTRICTED_ATTRIBUTE)),
        )

    if action == REMOTE_ADD_ACTION:
        return add_remote(
            name=cast(str, getattr(arguments, REMOTE_NAME_ATTRIBUTE)),
            url=cast(str, getattr(arguments, REMOTE_URL_ATTRIBUTE)),
            token_variable=cast(str, getattr(arguments, REMOTE_TOKEN_VARIABLE_ATTRIBUTE)),
        )

    if action == REMOTE_LIST_ACTION:
        return list_remotes()

    if action == REMOTE_REMOVE_ACTION:
        return remove_remote(cast(str, getattr(arguments, REMOTE_NAME_ATTRIBUTE)))

    if action != REMOTE_TOKEN_ACTION:
        return None

    token_action = cast(str | None, getattr(arguments, REMOTE_TOKEN_ACTION_ATTRIBUTE, None))

    if token_action == REMOTE_TOKEN_CREATE_ACTION:
        return create_remote_token(cast(str, getattr(arguments, REMOTE_TOKEN_NAME_ATTRIBUTE)))

    if token_action == REMOTE_TOKEN_LIST_ACTION:
        return list_remote_tokens(
            include_revoked=cast(bool, getattr(arguments, REMOTE_TOKEN_ALL_ATTRIBUTE)),
        )

    if token_action == REMOTE_TOKEN_REVOKE_ACTION:
        return revoke_remote_token(cast(str, getattr(arguments, REMOTE_TOKEN_NAME_ATTRIBUTE)))

    return None
