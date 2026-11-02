"""The worker's heartbeat file, and the health check that reads it (ADR 0107).

A live worker touches its heartbeat file before every receive and after every
extension of a running job's message. A health check reads how long ago that
was, with no server and no network.
"""

import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from azathoth.worker.errors import HeartbeatError

DEFAULT_MAX_HEARTBEAT_AGE_SECONDS: Final = 90
"""How old a heartbeat may be before its worker is unhealthy.

A worker beats at least every receive wait (at most 20 seconds) or every
extension (30 seconds by default), so 90 seconds allows for two missed
beats.
"""


class HeartbeatFile:
    """The file one worker touches to say it is alive."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path

    def beat(
        self,
    ) -> None:
        """Create the file, or move its modification time to now.

        Raises:
            HeartbeatError: The file cannot be written.
        """

        try:
            self.path.touch()
        except OSError as exc:
            raise HeartbeatError(
                f"Cannot write the heartbeat file {self.path}: {exc.strerror or exc}."
            ) from exc


class WorkerHealth(BaseModel):
    """What one health check found."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    healthy: bool
    age_seconds: float | None
    message: str


def check_heartbeat(
    path: Path,
    *,
    max_age_seconds: float,
    now: float | None = None,
) -> WorkerHealth:
    """Return whether a worker beat within `max_age_seconds` of now.

    A heartbeat from the future, as a skewed clock writes, is 0 seconds old.
    """

    try:
        beat_at = path.stat().st_mtime
    except OSError:
        return WorkerHealth(
            healthy=False,
            age_seconds=None,
            message=f"No heartbeat at {path}; the worker has not started, or cannot write it.",
        )

    age = max((now if now is not None else time.time()) - beat_at, 0.0)

    if age > max_age_seconds:
        return WorkerHealth(
            healthy=False,
            age_seconds=age,
            message=(
                f"The last heartbeat at {path} is {age:.0f} seconds old, "
                f"older than {max_age_seconds:g} seconds."
            ),
        )

    return WorkerHealth(
        healthy=True,
        age_seconds=age,
        message=f"The last heartbeat at {path} is {age:.0f} seconds old.",
    )


__all__ = [
    "DEFAULT_MAX_HEARTBEAT_AGE_SECONDS",
    "HeartbeatFile",
    "WorkerHealth",
    "check_heartbeat",
]
