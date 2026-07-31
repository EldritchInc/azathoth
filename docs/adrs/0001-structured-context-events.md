# ADR 0001: Represent context changes as events

## Status

Accepted

## Context

AI workflows frequently accumulate information across multiple steps.

Examples include:

- retrieved records;

- classifications;

- user answers;

- tool outputs;

- confidence estimates;

- evaluation results.

Representing context as an untracked mutable dictionary would make it difficult

to reconstruct why a strategy was selected or what information was available at

the time.

## Decision

Azathoth will represent context updates as typed, append-only events.

The current context will be derived from the ordered event history.

Each event should eventually support:

- a type;

- a payload;

- a producer;

- provenance;

- confidence;

- creation time.

## Consequences

Benefits:

- reproducible execution;

- causal debugging;

- regression replay;

- provenance tracking;

- future hierarchical oversight.

Costs:

- more domain modeling;

- materialization logic;

- additional storage;

- explicit conflict-handling requirements.