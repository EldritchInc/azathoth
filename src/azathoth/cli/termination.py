"""Stopping a command cleanly when it is interrupted or terminated (ADR 0105).

Ctrl-C raises `KeyboardInterrupt`; SIGTERM, where the platform sends it,
raises `CommandTerminated`. Either unwinds the command like any other
exception, so a run it is executing releases its lease on the way out and
can be resumed at once, and the command exits with the status a shell
expects: 130 when interrupted, 143 when terminated.
"""

import asyncio
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Final

INTERRUPTED_STATUS: Final = 130
"""The status of a command stopped by Ctrl-C: 128 plus SIGINT's number."""

TERMINATED_STATUS: Final = 143
"""The status of a command stopped by SIGTERM: 128 plus its number."""

INTERRUPTED_MESSAGE: Final = "Interrupted."
"""What a command stopped by Ctrl-C prints on stderr."""

TERMINATED_MESSAGE: Final = "Terminated."
"""What a command stopped by SIGTERM prints on stderr."""


class CommandTerminated(SystemExit):
    """The command received SIGTERM.

    It is a `SystemExit` with status 143, so code that lets it escape still
    exits as a terminated process does, and no `except Exception` catches it.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(TERMINATED_STATUS)


class _Termination:
    """Whether SIGTERM arrived inside the current block."""

    def __init__(
        self,
    ) -> None:
        self.requested = False

    def handle(
        self,
        signum: int,
        frame: FrameType | None,
    ) -> None:
        """Stop the command where it is.

        Inside a running event loop, every task is cancelled, as asyncio does
        for Ctrl-C, so each unwinds through its own cleanup; the block then
        raises `CommandTerminated`. Outside one, or on a second SIGTERM, it is
        raised at once.
        """

        if self.requested:
            raise CommandTerminated()

        self.requested = True

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise CommandTerminated() from None

        loop.call_soon_threadsafe(_cancel_every_task, loop)


def _cancel_every_task(
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Cancel every task of the loop that has not finished."""

    for task in asyncio.all_tasks(loop):
        task.cancel()


@contextmanager
def terminating_on_sigterm() -> Iterator[None]:
    """Turn SIGTERM into `CommandTerminated` inside the block.

    A run executing in an event loop is cancelled, so it releases its lease
    before the block raises. Outside the main thread, where Python cannot
    install a signal handler, nothing changes. The previous handler is
    restored when the block ends.
    """

    termination = _Termination()

    try:
        previous = signal.signal(signal.SIGTERM, termination.handle)
    except ValueError:
        yield
        return

    try:
        yield
    except asyncio.CancelledError:
        if termination.requested:
            raise CommandTerminated() from None

        raise
    finally:
        signal.signal(signal.SIGTERM, previous)


__all__ = [
    "INTERRUPTED_MESSAGE",
    "INTERRUPTED_STATUS",
    "TERMINATED_MESSAGE",
    "TERMINATED_STATUS",
    "CommandTerminated",
    "terminating_on_sigterm",
]
