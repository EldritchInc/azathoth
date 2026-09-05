# Context

`azathoth.context` defines Azathoth's immutable, event-backed execution context.

Context is not a mutable dictionary of application state.

It is an ordered history of traceable events.

```text
Context
  │
  ├── ContextEvent
  ├── ContextEvent
  ├── ContextEvent
  └── ...
```

The context package intentionally contains a very small domain surface:

- `Context`
- `ContextEvent`

These objects provide structured execution state without coupling that state to
strategies, workflows, model providers, evaluation, or optimization.

## Architectural Role

Azathoth passes execution state through explicit values.

```text
execution input
      │
      ▼
   Context
      │
      ▼
 executable behavior
      │
      ▼
 emitted ContextEvent objects
      │
      ▼
  new Context
```

The important property is:

```text
old Context
    ≠
new Context
```

Execution does not mutate a shared context object.

Instead, events are appended to produce a new immutable context value.

This gives higher-level execution infrastructure an ordered record of what
information existed and what was added during execution.

## ContextEvent

`ContextEvent` represents one traceable contribution to execution context.

It contains:

```text
ContextEvent
├── id
├── event_type
├── payload
├── producer
├── provenance
├── confidence
└── occurred_at
```

The model is immutable.

### Identity

Every event has a UUID identifier.

When an identifier is not supplied, one is generated automatically.

The identifier allows other events or execution artifacts to refer to a
specific contribution to context.

### Event Type

`event_type` is a required non-empty string.

It provides the semantic category used when executable behavior queries
context.

Examples may include:

```text
customer.message.received
customer.message.extracted
strategy.execution.started
strategy.execution.completed
```

The context package does not define a global event-type registry.

Event semantics belong to the components that produce and consume those
events.

### Payload

Each event contains a dictionary of JSON-compatible values.

```python
ContextEvent(
    event_type="customer.message.received",
    payload={
        "message": "I was charged twice.",
    },
    producer="support-api",
)
```

The payload boundary is intentionally JSON-compatible.

Context therefore carries structured data rather than arbitrary live Python
objects.

### Producer

Every event requires a non-empty `producer`.

```text
event
 └── producer
```

The producer identifies the component that contributed the event.

This makes context history attributable rather than representing information as
anonymous mutable state.

### Provenance

An event may include optional provenance.

For example, derived information can refer to the event from which it was
produced:

```python
ContextEvent(
    event_type="customer.message.extracted",
    payload={
        "value": "I was charged twice.",
    },
    producer="message-extraction-strategy",
    provenance=str(source_event.id),
)
```

The context model does not interpret provenance.

It records the value supplied by the producer.

This allows higher-level behavior to establish traceability without adding
hidden relationships inside `Context`.

### Confidence

An event may include an optional confidence value.

When supplied, confidence must be between:

```text
0.0 <= confidence <= 1.0
```

The context package stores confidence but does not decide what confidence
means or how it should affect execution.

Interpretation belongs to consuming behavior.

### Occurrence Time

Every event records `occurred_at`.

When no timestamp is supplied, Azathoth records the current timezone-aware UTC
time.

This timestamp describes when the event occurred.

Event ordering inside a `Context`, however, is represented directly by the
ordered event tuple.

## Context

`Context` is an immutable ordered tuple of `ContextEvent` objects.

```python
from azathoth.context import Context

context = Context()
```

Conceptually:

```text
Context
└── events: tuple[ContextEvent, ...]
```

An empty context contains no events.

A populated context preserves the supplied event order.

## Immutable Append

`Context.append()` returns a new context containing the supplied event.

```python
updated = context.append(event)
```

It does not modify the source context.

```text
Context A
    │
    │ append(event)
    │
    ├──────────────► Context B
    │
    ▼
unchanged
```

Conceptually:

```text
Context A
[event 1, event 2]

        +

event 3

        │
        ▼

Context B
[event 1, event 2, event 3]
```

while:

```text
Context A
[event 1, event 2]
```

remains unchanged.

This is the central state-transition operation provided by the context domain.

## Ordered History

Context event order is significant.

```text
events[0]
events[1]
events[2]
...
```

Azathoth preserves append order rather than reconstructing execution order from
timestamps.

This means context can represent a deterministic history such as:

```text
customer.message.received
        │
        ▼
strategy.execution.started
        │
        ▼
customer.message.extracted
        │
        ▼
strategy.execution.completed
```

The order is part of the context value itself.

## Querying by Event Type

`Context.by_type()` returns every event with the requested event type while
preserving context order.

```python
events = context.by_type(
    "customer.message.received",
)
```

Conceptually:

```text
Context
  │
  ├── type A ─────┐
  ├── type B      │
  ├── type A ─────┤
  └── type C      │
                  ▼
             (A, A)
```

The operation does not consume, remove, or modify matching events.

## Resolving the Latest Event

`Context.latest()` returns the most recently appended event matching an event
type.

```python
event = context.latest(
    "customer.message.received",
)
```

If no matching event exists, it returns `None`.

```text
Context
  │
  ├── request A
  ├── other event
  ├── request B
  └── other event
          │
          ▼
latest("request") = request B
```

This provides deterministic context-dependent lookup without introducing a
separate mutable "current value" store.

## Events Are the State

Context does not maintain two competing representations such as:

```text
event history
     +
mutable current-state dictionary
```

The event history is the context.

```text
Context
    =
ordered ContextEvent history
```

Components that need current information derive it from that history using
operations such as `latest()`.

This avoids synchronization problems between an event log and a separate
mutable state representation.

## Context Does Not Interpret Events

The context package records and retrieves events.

It does not decide what those events mean.

```text
Context
   │
   ├── stores
   ├── orders
   ├── appends
   └── queries
```

It does not:

```text
evaluate
score
route
retry
optimize
authorize
select models
execute tools
invoke providers
```

Those responsibilities belong to other Azathoth domains.

## Strategy Interaction

Strategies consume `Context`.

A strategy may produce additional `ContextEvent` objects as part of its
outcome.

```text
Context
   │
   ▼
Strategy
   │
   ▼
StrategyOutcome
   │
   ├── output
   ├── events
   └── metrics
```

Strategies do not need to mutate context directly.

They describe the events produced by their behavior.

Execution infrastructure decides how those events become part of recorded
execution context.

## Execution Lifecycle

`StrategyExecutor` demonstrates the complete context lifecycle.

Given an initial context:

```text
Initial Context
      │
      ▼
append strategy.execution.started
      │
      ▼
Execution Context
      │
      ▼
Strategy
      │
      ▼
StrategyOutcome.events
      │
      ▼
append emitted events in order
      │
      ▼
append strategy.execution.completed
      │
      ▼
Final Context
```

The executor records both the initial and final context in the resulting
execution evidence.

This makes the context transition observable.

## Initial and Final Context

Execution preserves the boundary:

```text
initial_context
      │
      ▼
execution
      │
      ▼
final_context
```

Because contexts are immutable, retaining the initial context does not require
copying or protecting a shared mutable state object from later modification.

The final context contains the ordered execution history added during the
operation.

## Strategy-Produced Events

When a strategy emits events, the executor appends them in the order supplied
by the strategy outcome.

```text
StrategyOutcome.events
        │
        ├── event A
        ├── event B
        └── event C
              │
              ▼
Final Context
        ...
        event A
        event B
        event C
        ...
```

The executor then appends its completion lifecycle event.

This preserves the relationship between executable behavior and the context
history that behavior produced.

## Workflow Context

Workflows build on the same context abstraction.

Workflow execution can propagate inputs and execution-produced events between
steps without introducing a separate shared mutable workflow-state object.

Conceptually:

```text
Workflow Input
      │
      ▼
Context
      │
      ▼
Step A
      │
      ▼
additional events
      │
      ▼
Context
      │
      ▼
Step B
```

The workflow layer owns workflow-specific propagation and orchestration.

The context layer only provides the immutable event history used by that
orchestration.

## Traceability

A context event can expose several independent traceability dimensions:

```text
id
    event identity

producer
    who created it

provenance
    where derived information came from

occurred_at
    when it occurred

position in Context.events
    execution-history order
```

These fields allow execution history to remain explicit without embedding
provider-specific tracing infrastructure into the context domain.

## Provider Independence

`Context` and `ContextEvent` contain no provider-specific model abstractions.

They do not depend on:

```text
OpenRouter
model catalogs
model portfolios
language-model registries
provider request objects
```

A provider-backed strategy may emit context events, but the resulting context
remains provider-neutral.

This allows deterministic strategies, tool-backed strategies, prompt-backed
strategies, and workflow infrastructure to use the same state representation.

## JSON-Compatible Data Boundary

Context payloads are JSON-compatible.

This is an intentional architectural constraint.

```text
arbitrary executable Python object
            ✗

structured JSON-compatible value
            ✓
```

Context is therefore a data boundary rather than an object-sharing mechanism.

Executable implementations remain outside the context domain.

## Context Is Not Persistence

The context package defines immutable domain values.

It does not define repositories or persistence policy.

```text
Context
ContextEvent
```

are domain objects.

Whether a higher-level artifact containing context is persisted belongs to that
artifact's owning subsystem.

For example, execution or workflow records may retain context as part of their
evidence without making `azathoth.context` itself a persistence service.

## Context Is Not Execution

Context represents execution state.

It does not execute behavior.

```text
Context
   ≠
StrategyExecutor
```

A context can exist independently of any particular strategy executor,
workflow runner, provider, or optimizer.

## Context Is Not Workflow State Authority

Context records execution-local information.

It is not durable production intent.

```text
Context
    execution state and history

WorkflowProductionState
    durable production execution authority
```

These concepts serve fundamentally different purposes.

Production state determines what production workflow should execute.

Context records information used and produced while execution occurs.

## Context Is Not Memory

V1 context should not be confused with a general-purpose long-term memory
system.

`Context` is an ordered execution-state value.

It does not independently provide:

```text
semantic retrieval
vector search
knowledge persistence
memory consolidation
cross-execution recall
```

Higher-level systems may construct those capabilities using their own domain
models and then contribute relevant information to execution through
`ContextEvent` objects.

## Public Surface

The V1 public context package exports:

```python
from azathoth.context import (
    Context,
    ContextEvent,
)
```

That intentionally small API reflects the package's narrow architectural
responsibility.

## V1 Context Principles

The V1 context architecture can be summarized as:

```text
immutable

ordered

event-backed

JSON-compatible

traceable

provider-neutral

execution-oriented
```

The central distinction is:

```text
Context
    does not hide changing state

Context
    records an ordered history of explicit contributions
```

That gives Azathoth a common execution-state boundary that can be passed through
strategies and workflows without introducing shared mutable state or coupling
the context domain to the systems that interpret it.