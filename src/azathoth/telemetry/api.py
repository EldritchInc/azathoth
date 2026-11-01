"""The tracing interface the engine uses, and its no-op default (ADR 0100).

The engine never imports OpenTelemetry. It talks to a `Telemetry`, which is
`NO_TELEMETRY` unless tracing is configured, so untraced commands pay for
nothing.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Protocol

AttributeValue = str | bool | int | float
"""A span attribute value: never content, only identifiers and measurements."""

Attributes = Mapping[str, AttributeValue]


class TelemetrySpan(Protocol):
    """One span, started by a `Telemetry`."""

    def set_attributes(
        self,
        attributes: Attributes,
    ) -> None:
        """Set attributes on the span."""

        ...

    def add_event(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        """Record one event on the span."""

        ...

    def set_error(
        self,
        error_type: str,
    ) -> None:
        """Mark the span failed, naming the type of what failed, never its message."""

        ...

    def end(
        self,
        *,
        end_time: datetime | None = None,
    ) -> None:
        """End the span."""

        ...


class Telemetry(Protocol):
    """Start spans, make them current, and propagate their trace context."""

    @property
    def enabled(
        self,
    ) -> bool:
        """Return whether spans are exported."""

        ...

    def start_span(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        parent: TelemetrySpan | None = None,
        start_time: datetime | None = None,
    ) -> TelemetrySpan:
        """Start one span under a parent, or under the current span when none is given."""

        ...

    def activate(
        self,
        span: TelemetrySpan,
    ) -> object:
        """Make one span current in this context, returning a token for `deactivate`."""

        ...

    def deactivate(
        self,
        token: object,
    ) -> None:
        """Restore the context `activate` replaced."""

        ...

    def trace_context(
        self,
        span: TelemetrySpan | None = None,
    ) -> dict[str, str]:
        """Return the W3C trace context of a span, or of the current one.

        The keys are `TRACEPARENT` and, when there is one, `TRACESTATE`, ready
        to put in a child process's environment. It is empty when there is
        nothing to propagate.
        """

        ...

    def shutdown(
        self,
    ) -> None:
        """Export every finished span and stop."""

        ...


class _NoSpan:
    """A span that records nothing."""

    def set_attributes(
        self,
        attributes: Attributes,
    ) -> None:
        return None

    def add_event(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        return None

    def set_error(
        self,
        error_type: str,
    ) -> None:
        return None

    def end(
        self,
        *,
        end_time: datetime | None = None,
    ) -> None:
        return None


NO_SPAN = _NoSpan()
"""The span every `NoTelemetry` returns."""


class NoTelemetry:
    """Telemetry that records and exports nothing; the default."""

    @property
    def enabled(
        self,
    ) -> bool:
        """Return False: nothing is exported."""

        return False

    def start_span(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        parent: TelemetrySpan | None = None,
        start_time: datetime | None = None,
    ) -> TelemetrySpan:
        """Return the span that records nothing."""

        return NO_SPAN

    def activate(
        self,
        span: TelemetrySpan,
    ) -> object:
        """Return a token that restores nothing."""

        return None

    def deactivate(
        self,
        token: object,
    ) -> None:
        """Restore nothing."""

        return None

    def trace_context(
        self,
        span: TelemetrySpan | None = None,
    ) -> dict[str, str]:
        """Return no trace context."""

        return {}

    def shutdown(
        self,
    ) -> None:
        """Do nothing."""

        return None


NO_TELEMETRY = NoTelemetry()
"""The telemetry used when tracing is not configured."""

_active: list[Telemetry] = [NO_TELEMETRY]


def active_telemetry() -> Telemetry:
    """Return the telemetry this process traces with."""

    return _active[0]


def use_telemetry(
    telemetry: Telemetry,
) -> Telemetry:
    """Make one telemetry the one this process traces with, returning the previous one."""

    previous = _active[0]
    _active[0] = telemetry

    return previous


@contextmanager
def traced(
    telemetry: Telemetry,
    name: str,
    attributes: Attributes | None = None,
) -> Iterator[TelemetrySpan]:
    """Run a block inside one current span.

    An exception escaping the block marks the span failed with the
    exception's type, never its message, and is raised again.
    """

    span = telemetry.start_span(name, attributes)
    token = telemetry.activate(span)

    try:
        yield span
    except BaseException as exc:
        span.set_error(type(exc).__name__)

        raise
    finally:
        telemetry.deactivate(token)
        span.end()


__all__ = [
    "NO_SPAN",
    "NO_TELEMETRY",
    "AttributeValue",
    "Attributes",
    "NoTelemetry",
    "Telemetry",
    "TelemetrySpan",
    "active_telemetry",
    "traced",
    "use_telemetry",
]
