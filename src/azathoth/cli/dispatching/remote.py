"""Remote command dispatch for the Azathoth CLI (ADR 0124)."""

from argparse import Namespace
from collections.abc import Callable
from typing import cast

from azathoth.cli.parsing import (
    REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE,
    REMOTE_ACTION_ATTRIBUTE,
    REMOTE_HOST_ATTRIBUTE,
    REMOTE_PORT_ATTRIBUTE,
    REMOTE_SERVE_ACTION,
    REMOTE_TOKEN_ACTION,
    REMOTE_TOKEN_ACTION_ATTRIBUTE,
    REMOTE_TOKEN_ALL_ATTRIBUTE,
    REMOTE_TOKEN_CREATE_ACTION,
    REMOTE_TOKEN_LIST_ACTION,
    REMOTE_TOKEN_NAME_ATTRIBUTE,
    REMOTE_TOKEN_REVOKE_ACTION,
)

RemoteTokenNameHandler = Callable[[str], int]
RemoteTokenListHandler = Callable[..., int]
RemoteServeHandler = Callable[..., int]


def dispatch_remote_command(
    arguments: Namespace,
    *,
    create_remote_token: RemoteTokenNameHandler,
    list_remote_tokens: RemoteTokenListHandler,
    revoke_remote_token: RemoteTokenNameHandler,
    serve_remote: RemoteServeHandler,
) -> int | None:
    """Dispatch one parsed remote command, or return None for one not given in full."""

    action = cast(str | None, getattr(arguments, REMOTE_ACTION_ATTRIBUTE, None))

    if action == REMOTE_SERVE_ACTION:
        return serve_remote(
            host=cast(str, getattr(arguments, REMOTE_HOST_ATTRIBUTE)),
            port=cast(int, getattr(arguments, REMOTE_PORT_ATTRIBUTE)),
            accept_restricted=cast(bool, getattr(arguments, REMOTE_ACCEPT_RESTRICTED_ATTRIBUTE)),
        )

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
