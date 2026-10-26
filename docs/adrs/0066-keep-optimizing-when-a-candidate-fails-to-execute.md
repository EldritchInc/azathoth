# ADR 0066: Keep Optimizing When a Candidate Fails to Execute

- Status: Accepted
- Date: 2026-09-07
- Decided in: #82

## Context

Optimization deliberately tries candidates that may not work: cheaper models,
different bindings, untested combinations. Some of them will fail at run time,
through provider errors, timeouts, malformed output or failing tools.

If one failing candidate aborted the whole optimization session, the evidence
already gathered about every other candidate would be lost, and the riskiest
proposals would block the search entirely.

## Decision

A candidate's execution failure is evidence about that candidate, not a
failure of the optimization session.

When a candidate's run fails, the experiment records the failed run, judges it
as a failed result, and keeps that candidate in the ranking. The session goes
on executing the remaining candidates and generations.

A failed candidate therefore competes, and loses, on the same footing as every
other candidate. How a failed run is judged and scored is refined by ADR 0073.

Failures that happen before any candidate executes are different. An empty
benchmark, an unsupported comparison, or a candidate without a declared result
is rejected up front, because no evidence could be produced.

## Consequences

### Positive

- Risky proposals cannot destroy evidence about safe ones.
- Failure becomes visible in rankings and history rather than in a crash.
- Every candidate's run is recorded, including failed ones.

### Negative

- A session can complete with every candidate failing; a completed session is
  not proof that anything worked.

## Alternatives Considered

### Abort optimization on the first candidate failure

Rejected. One bad proposal would discard the whole session's evidence.

### Drop failed candidates from the ranking

Rejected. Failure would become invisible, and a ranking would silently cover
fewer candidates than were tried.
