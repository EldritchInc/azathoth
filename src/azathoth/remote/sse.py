"""Server-sent events, as a remote streams a job's events and a client reads them (ADR 0138).

This module needs no web framework, so a client reads a stream with it.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerSentEvent:
    """One event a stream sent: its name, its data, and its ID."""

    name: str | None
    data: str
    event_id: str | None


def read_server_sent(
    lines: Iterable[str],
) -> Iterator[ServerSentEvent]:
    """Yield the events a stream's lines send, each once the blank line ending it is read.

    A comment, a line starting `:`, is skipped; an event the stream ends
    before finishing is not yielded, as a browser does not dispatch one.
    """

    name: str | None = None
    data: list[str] = []
    event_id: str | None = None

    for raw in lines:
        line = raw.rstrip("\r")

        if not line:
            if data or name is not None:
                yield ServerSentEvent(name=name, data="\n".join(data), event_id=event_id)

            name, data, event_id = None, [], None
            continue

        if line.startswith(":"):
            continue

        field, _, value = line.partition(":")
        value = value.removeprefix(" ")

        if field == "event":
            name = value
        elif field == "data":
            data.append(value)
        elif field == "id":
            event_id = value


__all__ = [
    "ServerSentEvent",
    "read_server_sent",
]
