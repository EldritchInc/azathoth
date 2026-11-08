"""Progress notifications while a tool call's invocation runs (ADR 0111).

A tool call waits for its invocation to finish. Meanwhile, the client is
told as each of the workflow's steps finishes, so a long run shows that it
is alive. Progress counts the workflow's own steps; a child workflow's steps
run in their own process and are not counted.
"""

import asyncio
import concurrent.futures
from collections.abc import Callable, Coroutine
from typing import Any

from azathoth import api

ReportProgress = Callable[[float, float | None, str | None], Coroutine[Any, Any, None]]
"""Send the client one progress notification: progress, total and a message."""


def progress_message(
    finished: int,
    total: int,
) -> str:
    """Return the message of one progress notification."""

    return f"{finished} of {total} steps finished."


class StepProgress:
    """Report each finished step of one invocation to the client.

    The invocation runs on a worker thread, and its events arrive there, so
    each notification is handed to the call's event loop, and `flush` waits
    for every one before the call returns its result. A notification that
    fails is dropped: progress never changes a result.
    """

    def __init__(
        self,
        report: ReportProgress,
        *,
        total: int,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        if total < 1:
            raise ValueError("A run's progress counts at least one step.")

        self._report = report
        self._total = total
        self._loop = loop
        self._finished = 0
        self._pending: list[concurrent.futures.Future[None]] = []

    def observe(
        self,
        event: api.RunEvent,
    ) -> None:
        """Send a notification for one finished step, from any thread."""

        if not isinstance(event, api.StepFinished):
            return

        self._finished = min(self._finished + 1, self._total)

        self._pending.append(
            asyncio.run_coroutine_threadsafe(
                self._report(
                    float(self._finished),
                    float(self._total),
                    progress_message(self._finished, self._total),
                ),
                self._loop,
            )
        )

    async def flush(
        self,
    ) -> None:
        """Wait for every notification sent so far, ignoring any that failed."""

        pending, self._pending = self._pending, []

        await asyncio.gather(
            *(asyncio.wrap_future(future) for future in pending),
            return_exceptions=True,
        )


__all__ = [
    "ReportProgress",
    "StepProgress",
    "progress_message",
]
