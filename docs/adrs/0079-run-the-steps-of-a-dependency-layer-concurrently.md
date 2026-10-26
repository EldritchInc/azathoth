# ADR 0079: Run the Steps of a Dependency Layer Concurrently

- Status: Accepted
- Date: 2026-10-25
- Decided in: #100

## Context

ADR 0017 groups workflow steps into dependency layers, and specified that
steps in one layer behave as though they ran concurrently. Its first
implementation ran them one at a time, and listed that as a known limitation.

Sequential layers make independent provider calls and tools wait on one
another. They also make redundant producers (ADR 0080) pointless, since the
fallback cannot race the primary.

## Decision

The eligible steps of one layer execute concurrently, in an
`asyncio.TaskGroup`, each from the same layer context.

A layer commits only after every one of its steps has finished, and commits
follow declared step order. The recorded `WorkflowRun` and its final context
are therefore identical whatever order the steps finish in.

A `fail_workflow` failure does not cancel its siblings. They finish and are
recorded, and then the run stops before the next layer. When several steps of
one layer fail under `fail_workflow`, the first in declared order is the
failure the run reports. Steps expected to fail, such as redundant producers,
use `continue`.

There is no concurrency limit inside a layer, and none configured outside the
specification. The width of the specification bounds it, which keeps runs
reproducible from the specification alone.

## Consequences

### Positive

- Independent steps no longer wait on each other.
- Evidence is deterministic despite concurrent execution.
- Siblings of a halting step still leave complete evidence.

### Negative

- A very wide layer makes that many concurrent provider calls.
- A halting failure does not save the cost of its running siblings.

## Alternatives Considered

### Cancel siblings when one step halts the run

Rejected. Their evidence would be lost, and the recorded run would depend on
timing.

### Configure a concurrency limit outside the specification

Rejected. The same specification would behave differently on different
machines.
