# Context

`azathoth.context` provides immutable, event-backed working context for Azathoth executions.

Context is not a mutable dictionary of application state.

It is an ordered history of traceable events.

## Purpose

Strategies, workflows, and future optimization systems need structured information without relying on shared mutable state.

Azathoth represents that information using:

- `Context`
- `ContextEvent`

Each event records what happened, who produced it, and optional provenance and confidence information.

## Core Concepts

### ContextEvent

A `ContextEvent` represents one contribution to working context.

```python
from azathoth.context import ContextEvent

event = ContextEvent(
    event_type="request.received",
    payload={
        "text": "Explain deterministic optimization.",
    },
    producer="example",
)
```

Events contain:

- a unique identifier;
- an event type;
- a JSON-compatible payload;
- a producer;
- optional provenance;
- optional confidence; and
- an occurrence timestamp.

Events are immutable.

### Context

`Context` is an immutable ordered collection of events.

```python
from azathoth.context import Context

context = Context()
context = context.append(event)
```

Appending an event returns a new context rather than modifying the existing one.

```text
Context A
   │
   │ append event
   ▼
Context B
```

The original context remains unchanged.

## Querying Context

Events can be retrieved by type:

```python
events = context.by_type("request.received")
```

The latest matching event can also be requested:

```python
event = context.latest("request.received")
```

This pattern is used throughout Azathoth to resolve context-dependent behavior deterministically.

## Provenance

Context events may record where information originated.

```python
derived = ContextEvent(
    event_type="analysis.completed",
    payload={
        "answer": "result",
    },
    producer="analysis-strategy",
    provenance=str(source_event.id),
)
```

Provenance makes derived context traceable without embedding hidden mutable state.

## Typical Flow

```text
Initial Context
      │
      ▼
ContextEvent
      │
      ▼
append()
      │
      ▼
New Context
      │
      ▼
Strategy
      │
      ▼
Additional Events
```

Strategies can consume one context and return events that become part of later execution history.

## Design Principles

The context domain is intentionally:

- immutable;
- ordered;
- event-backed;
- JSON-compatible;
- traceable; and
- independent of any model provider.

Context does not decide how events should be interpreted.

It only provides structured execution state.

## Relationship to Other Packages

[`azathoth.strategies`](../strategies/README.md) consume `Context` objects during execution.

[`azathoth.execution`](../execution/README.md) records initial and final context around strategy execution.

[`azathoth.workflows`](../workflows/README.md) uses context to propagate workflow inputs and execution events between steps.

See the [project README](../../../README.md) for the complete Azathoth architecture.