# ADR 0064: Keep Production Revisions as Audit History, Not Authority

- Status: Accepted
- Date: 2026-09-03
- Decided in: #72, #74

## Context

Every promotion should leave a durable record: what was deployed and when.
The tempting design is to make the newest record define production, or to keep
an "active revision" pointer.

Both designs make history double as authority. A correction to history, a
backfilled record, or a pointer bug would then change what production runs.

## Decision

Promotion persists two different things:

```text
WorkflowProductionState
    current production intent: what production executes

WorkflowProductionRevision
    immutable deployment history: what was deployed, and when
```

Revisions are persisted through `WorkflowProductionRevisionRepository`
(`InMemoryWorkflowProductionRevisionRepository` and
`SQLiteWorkflowProductionRevisionRepository`). They are audit history only.

Production execution reads `WorkflowProductionState` and nothing else. It
never asks for the newest revision and never follows an active-revision
pointer.

The CLI reads the two separately: `workflow production` shows the active
state, and `workflow revisions` lists deployment history, newest first.

## Consequences

### Positive

- History can be read, exported and audited without affecting production.
- The question "what runs now?" has exactly one answer.

### Negative

- State and the latest revision describe the same promotion twice, and tools
  must not assume they always agree.

## Alternatives Considered

### Execute the newest revision

Rejected. History would become authority.

### Store an active-revision pointer

Rejected. Authority would hinge on a pointer into history rather than on an
explicit state.
