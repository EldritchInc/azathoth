"""A sleep the tests end by hand, so a worker's extensions happen when they say (ADR 0107).

A worker sleeps between extensions. Given `Ticks.sleep` in place of
`asyncio.sleep`, each of its sleeps waits until a test calls `tick`, so a
test decides exactly how many extensions happen, and when, on every
platform's timer alike.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

UNTIL_TIMEOUT_SECONDS = 10.0
"""How long `until` waits for a condition before failing the test."""


async def until(
    condition: Callable[[], bool],
    *,
    timeout: float = UNTIL_TIMEOUT_SECONDS,
) -> None:
    """Wait until a condition holds, failing the test if it never does."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while not condition():
        assert loop.time() < deadline, "the condition never held"
        await asyncio.sleep(0.001)


@dataclass
class Ticks:
    """Stands in for `asyncio.sleep`: every sleep lasts until the next tick.

    `requested` holds the seconds every sleep asked for, in order, and
    `cancelled` counts the sleeps cancelled before their tick.
    """

    requested: list[float] = field(default_factory=list)
    cancelled: int = 0
    pending: asyncio.Future[None] | None = None

    async def sleep(
        self,
        seconds: float,
    ) -> None:
        """Sleep until the next tick."""

        self.requested.append(seconds)
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.pending = future

        try:
            await future
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.pending = None

    def waiting(self) -> bool:
        """Return whether a sleep is waiting for its tick."""

        return self.pending is not None and not self.pending.done()

    async def tick(self) -> None:
        """Wait for a sleep to be waiting, then end it."""

        await until(self.waiting)

        assert self.pending is not None
        self.pending.set_result(None)
