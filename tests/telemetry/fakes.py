"""Test doubles for tracing: a recording Telemetry, and a minimal OpenTelemetry API tracer."""

import itertools
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import (
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
)
from opentelemetry.util import types

from azathoth.telemetry import Attributes, AttributeValue, TelemetrySpan

#
# A recording Telemetry, for tests of what the engine traces.
#


@dataclass
class RecordedEvent:
    """One event recorded on a span."""

    name: str
    attributes: dict[str, AttributeValue]
    timestamp: datetime | None


@dataclass
class RecordedSpan:
    """One span a RecordingTelemetry started."""

    name: str
    number: int
    parent: "RecordedSpan | None"
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    events: list[RecordedEvent] = field(default_factory=list)
    error_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    ended: bool = False
    end_order: int | None = None
    end_counter: "itertools.count[int] | None" = None

    def set_attributes(
        self,
        attributes: Attributes,
    ) -> None:
        self.attributes.update(attributes)

    def add_event(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        self.events.append(RecordedEvent(name, dict(attributes or {}), timestamp))

    def set_error(
        self,
        error_type: str,
    ) -> None:
        self.error_type = error_type

    def end(
        self,
        *,
        end_time: datetime | None = None,
    ) -> None:
        assert not self.ended, f"span {self.name} ended twice"

        self.ended = True
        self.end_time = end_time

        if self.end_counter is not None:
            self.end_order = next(self.end_counter)


class RecordingTelemetry:
    """Telemetry that keeps every span in order, with its parent."""

    def __init__(
        self,
    ) -> None:
        self.spans: list[RecordedSpan] = []
        self.shut_down = False
        self._current: ContextVar[RecordedSpan | None] = ContextVar("current", default=None)
        self._counter = itertools.count(1)
        self._ends = itertools.count(1)

    @property
    def enabled(
        self,
    ) -> bool:
        return True

    def start_span(
        self,
        name: str,
        attributes: Attributes | None = None,
        *,
        parent: TelemetrySpan | None = None,
        start_time: datetime | None = None,
    ) -> RecordedSpan:
        resolved = parent if parent is not None else self._current.get()

        assert resolved is None or isinstance(resolved, RecordedSpan)

        span = RecordedSpan(
            name=name,
            number=next(self._counter),
            parent=resolved,
            attributes=dict(attributes or {}),
            start_time=start_time,
            end_counter=self._ends,
        )

        self.spans.append(span)

        return span

    def activate(
        self,
        span: TelemetrySpan,
    ) -> object:
        assert isinstance(span, RecordedSpan)

        return self._current.set(span)

    def deactivate(
        self,
        token: object,
    ) -> None:
        assert isinstance(token, Token)

        self._current.reset(token)

    def trace_context(
        self,
        span: TelemetrySpan | None = None,
    ) -> dict[str, str]:
        resolved = span if span is not None else self._current.get()

        if resolved is None:
            return {}

        assert isinstance(resolved, RecordedSpan)

        return {"TRACEPARENT": f"00-{'0' * 31}1-{resolved.number:016x}-01"}

    def shutdown(
        self,
    ) -> None:
        self.shut_down = True

    def named(
        self,
        name: str,
    ) -> list[RecordedSpan]:
        """Return every recorded span with one name, in start order."""

        return [span for span in self.spans if span.name == name]


#
# A minimal OpenTelemetry API tracer, for tests of the OpenTelemetry adapter
# where the SDK is not installed.
#


@dataclass
class FakeApiEvent:
    """One event an API span recorded."""

    name: str
    attributes: dict[str, Any]
    timestamp: int | None


class FakeApiSpan(trace.Span):
    """An API span that records everything it is told."""

    def __init__(
        self,
        name: str,
        context: SpanContext,
        parent: SpanContext | None,
        attributes: Mapping[str, Any] | None,
        start_time: int | None,
    ) -> None:
        self.name = name
        self.context = context
        self.parent = parent
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.events: list[FakeApiEvent] = []
        self.status: Status | None = None
        self.start_time = start_time
        self.end_time: int | None = None
        self.ended = False

    def end(
        self,
        end_time: int | None = None,
    ) -> None:
        self.ended = True
        self.end_time = end_time

    def get_span_context(
        self,
    ) -> SpanContext:
        return self.context

    def set_attributes(
        self,
        attributes: Mapping[str, types.AttributeValue],
    ) -> None:
        self.attributes.update(attributes)

    def set_attribute(
        self,
        key: str,
        value: types.AttributeValue,
    ) -> None:
        self.attributes[key] = value

    def add_event(
        self,
        name: str,
        attributes: types.Attributes = None,
        timestamp: int | None = None,
    ) -> None:
        self.events.append(FakeApiEvent(name, dict(attributes or {}), timestamp))

    def update_name(
        self,
        name: str,
    ) -> None:
        self.name = name

    def is_recording(
        self,
    ) -> bool:
        return not self.ended

    def set_status(
        self,
        status: Status | StatusCode,
        description: str | None = None,
    ) -> None:
        self.status = status if isinstance(status, Status) else Status(status, description)

    def record_exception(
        self,
        exception: BaseException,
        attributes: types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        raise AssertionError("Azathoth never records exceptions, which may quote content.")


class FakeApiTracer:
    """A tracer whose spans are FakeApiSpans, numbered in start order."""

    def __init__(
        self,
    ) -> None:
        self.spans: list[FakeApiSpan] = []
        self._ids = itertools.count(1)

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        *,
        attributes: types.Attributes = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> FakeApiSpan:
        parent = trace.get_current_span(context).get_span_context()
        parent_context = parent if parent.is_valid else None

        span = FakeApiSpan(
            name,
            SpanContext(
                trace_id=parent.trace_id if parent_context is not None else next(self._ids) << 64,
                span_id=next(self._ids),
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            ),
            parent_context,
            attributes,
            start_time,
        )

        assert record_exception is False, "Azathoth never records exceptions."
        assert set_status_on_exception is False, "Azathoth sets error status itself."

        self.spans.append(span)

        return span
