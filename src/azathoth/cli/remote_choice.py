"""The remote a command runs on, once `--remote` has chosen one (ADR 0140).

`main` chooses the remote for the command it runs, and every service API
instance the command asks for is then the one connected to it. A command
that asks for this machine's database itself while a remote is chosen is
refused, so it never reads here what it was asked to read there. The
connected instance is closed when the command ends.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final

from azathoth import api
from azathoth.cli.configuration import CliRuntimeConfiguration


class RemoteChosenError(Exception):
    """A command asked for this machine's database while it runs on a remote."""


LOCAL_DATABASE_MESSAGE: Final = (
    "This command reads this machine's database itself, which --remote does not reach."
)
"""What a command that asks for this machine's database while a remote is chosen says."""


class _Choice:
    """The remote chosen for one command, and the instance connected to it once asked for."""

    def __init__(
        self,
        target: str,
    ) -> None:
        self.target = target
        self.instance: api.ConnectedInstance | None = None


_CHOSEN: ContextVar[_Choice | None] = ContextVar("azathoth_cli_remote", default=None)


def chosen_remote() -> str | None:
    """Return the remote the running command was given, by its name or URL, or None."""

    choice = _CHOSEN.get()

    return None if choice is None else choice.target


def refuse_local_database() -> None:
    """Refuse a command that asks for this machine's database while a remote is chosen.

    Raises:
        RemoteChosenError: A remote is chosen.
    """

    if _CHOSEN.get() is not None:
        raise RemoteChosenError(LOCAL_DATABASE_MESSAGE)


@contextmanager
def choosing(
    target: str | None,
) -> Iterator[None]:
    """Run what this context holds on the remote `target` names, or on this machine for None.

    The instance connected to the remote, when one was asked for, is closed
    as the context ends.
    """

    choice = None if target is None else _Choice(target)
    token = _CHOSEN.set(choice)

    try:
        yield
    finally:
        _CHOSEN.reset(token)

        if choice is not None and choice.instance is not None:
            choice.instance.close()


def connected_instance(
    configuration: CliRuntimeConfiguration,
    local: Callable[[CliRuntimeConfiguration], api.Azathoth],
) -> api.ConnectedInstance | None:
    """Return the instance connected to the chosen remote, or None when none is chosen.

    The remote is found by its name among the remotes of `local`'s
    instance, or by its URL, with its token as a push reaches it. One
    command asks for it once; every later ask is given the same instance.

    Raises:
        InvalidArgumentError: The URL is not an http or https URL, or no
            token is given or set.
        NotFoundError: No remote has the name.
    """

    choice = _CHOSEN.get()

    if choice is None:
        return None

    if choice.instance is None:
        choice.instance = local(configuration).remote(choice.target).connect()

    return choice.instance


__all__ = [
    "LOCAL_DATABASE_MESSAGE",
    "RemoteChosenError",
    "choosing",
    "chosen_remote",
    "connected_instance",
    "refuse_local_database",
]
