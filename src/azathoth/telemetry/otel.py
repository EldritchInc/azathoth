"""Telemetry backed by the OpenTelemetry API (ADR 0100).

Only `opentelemetry-api` is used here. Which SDK, exporter and resource it
exports through is decided in `azathoth.telemetry.sdk`.
"""

from collections.abc import Callable, Mapping
from contextvars import Token
from datetime import datetime
from typing import Protocol, cast

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util import types

from azathoth.telemetry.api import Attributes, TelemetrySpan
from azathoth.telemetry.conventions import ERROR_TYPE

TRACEPARENT_VARIABLE = "TRACEPARENT"
"""The environment variable carrying a W3C `traceparent` to a child process."""

TRACESTATE_VARIABLE = "TRACESTATE"
"""The environment variable carrying a W3C `tracestate` to a child process."""

_PROPAGATOR = TraceContextTextMapPropagator()


class SpanStarter(Protocol):
    """What Azathoth needs of an OpenTelemetry tracer: starting spans explicitly."""

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        *,
        attributes: types.Attributes = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> trace.Span:
        """Start one span."""

        ...


def _nanoseconds(
    moment: datetime | None,
) -> int | None:
    """Return one moment in nanoseconds since the epoch, as OpenTelemetry takes it."""

    if moment is None:
        return None

    return int(moment.timestamp() * 1_000_000_000)


class OpenTelemetrySpan:
    """One Azathoth span backed by an OpenTelemetry span."""

    def __init__(
        self,
        span: trace.Span,
    ) -> None:
        self.span = span

    def set_attributes(
        self,
        attributes: Attributes,
    ) -> None:
        """Set attributes on the span."""

        self.span.set_attributes(dict(attributes))

    def add_event(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        """Record one event on the span."""

        self.span.add_event(
            name,
            dict(attributes) if attributes is not None else None,
            timestamp=_nanoseconds(timestamp),
        )

    def set_error(
        self,
        error_type: str,
    ) -> None:
        """Mark the span failed, naming the type of what failed."""

        self.span.set_status(Status(StatusCode.ERROR))
        self.span.set_attribute(ERROR_TYPE, error_type)

    def end(
        self,
        *,
        end_time: datetime | None = None,
    ) -> None:
        """End the span."""

        self.span.end(end_time=_nanoseconds(end_time))


def extract_trace_context(
    environ: Mapping[str, str],
) -> Context | None:
    """Return the trace context a parent process passed in its environment, if any."""

    traceparent = environ.get(TRACEPARENT_VARIABLE)

    if not traceparent:
        return None

    carrier = {"traceparent": traceparent}

    tracestate = environ.get(TRACESTATE_VARIABLE)

    if tracestate:
        carrier["tracestate"] = tracestate

    context = _PROPAGATOR.extract(carrier)

    if not trace.get_current_span(context).get_span_context().is_valid:
        return None

    return context


class OpenTelemetryTelemetry:
    """Telemetry that starts OpenTelemetry spans from one tracer.

    A span started without a parent while no span is current continues the
    trace context this process was started with, so a child `azathoth`
    continues its parent's trace.
    """

    def __init__(
        self,
        tracer: SpanStarter,
        *,
        parent_context: Context | None = None,
        shutdown: Callable[[], None] | None = None,
    ) -> None:
        self._tracer = tracer
        self._parent_context = parent_context
        self._shutdown = shutdown

    @property
    def enabled(
        self,
    ) -> bool:
        """Return True: spans are exported."""

        return True

    def start_span(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        parent: TelemetrySpan | None = None,
        start_time: datetime | None = None,
    ) -> OpenTelemetrySpan:
        """Start one span under a parent, the current span, or the inherited trace."""

        span = self._tracer.start_span(
            name,
            context=self._parent_of(parent),
            attributes=dict(attributes) if attributes is not None else None,
            start_time=_nanoseconds(start_time),
            record_exception=False,
            set_status_on_exception=False,
        )

        return OpenTelemetrySpan(span)

    def activate(
        self,
        span: TelemetrySpan,
    ) -> object:
        """Make one span current in this context."""

        return otel_context.attach(trace.set_span_in_context(self._unwrap(span)))

    def deactivate(
        self,
        token: object,
    ) -> None:
        """Restore the context `activate` replaced."""

        otel_context.detach(cast(Token[Context], token))

    def trace_context(
        self,
        span: TelemetrySpan | None = None,
    ) -> dict[str, str]:
        """Return the W3C trace context of a span, or of the current one."""

        context = trace.set_span_in_context(self._unwrap(span)) if span is not None else None

        carrier: dict[str, str] = {}

        _PROPAGATOR.inject(carrier, context=context)

        environment = {}

        if "traceparent" in carrier:
            environment[TRACEPARENT_VARIABLE] = carrier["traceparent"]

        if carrier.get("tracestate"):
            environment[TRACESTATE_VARIABLE] = carrier["tracestate"]

        return environment

    def shutdown(
        self,
    ) -> None:
        """Export every finished span and stop."""

        if self._shutdown is not None:
            self._shutdown()

    def _parent_of(
        self,
        parent: TelemetrySpan | None,
    ) -> Context | None:
        """Return the context a new span starts under."""

        if parent is not None:
            return trace.set_span_in_context(self._unwrap(parent))

        if trace.get_current_span().get_span_context().is_valid:
            return None

        return self._parent_context

    @staticmethod
    def _unwrap(
        span: TelemetrySpan,
    ) -> trace.Span:
        """Return the OpenTelemetry span behind one of this telemetry's spans."""

        if not isinstance(span, OpenTelemetrySpan):
            raise TypeError("OpenTelemetryTelemetry only accepts spans it started.")

        return span.span


__all__ = [
    "TRACEPARENT_VARIABLE",
    "TRACESTATE_VARIABLE",
    "OpenTelemetrySpan",
    "SpanStarter",
    "OpenTelemetryTelemetry",
    "extract_trace_context",
]
