# ADR 0002: Use immutable domain models

## Status

Accepted

## Context

Azathoth must be able to reproduce optimization experiments and explain which
information was available at each execution step.

Mutable domain objects can change after they have been recorded or passed to
another component. This makes historical traces difficult to trust and can
produce subtle differences during replay.

## Decision

Core domain models will be immutable by default.

Context updates will return a new `Context` value containing the appended event
rather than modifying an existing context in place.

## Consequences

Benefits:

- state transitions are explicit;
- historical values remain trustworthy;
- tests can compare before and after states;
- replay behavior is easier to reason about;
- concurrent execution has fewer shared-mutation hazards.

Costs:

- updates create new model values;
- deeply nested payload values require separate discipline;
- developers must intentionally retain the returned updated context.