# ADR 0076: Import Append-Only Revisions Identified by Content Digests

- Status: Accepted
- Date: 2026-10-23
- Decided in: #99, #100

## Context

ADRs 0041, 0049 and 0055 made tools, benchmark datasets and workflows durable,
and each rejected saving a second artifact under an existing identifier. That
protected history from silent overwrites, but it left no way to change a
workflow, a tool or a benchmark at all, short of inventing a new identity.

Evidence also needs to name exactly what it judged. "Workflow X" is not
enough once workflow X can change.

## Decision

Every import appends a revision. Nothing is ever edited in place, and nothing
is rejected merely for already existing.

The identity is a lineage:

```text
workflow     <WORKFLOW_ID>             revisions 1, 2, 3 …
tool         <TOOL_ID>@<VERSION>       revisions 1, 2, 3 …
benchmark    <BENCHMARK_ID>            revisions 1, 2, 3 …
```

Each revision records its number, its content, a `content_digest` (sha256 of
the canonical JSON, so key order and file formatting do not matter) and its
import time. The latest revision is current: execution, optimization,
promotion and benchmarks always use it.

Re-importing earlier content appends a revision whose digest matches, and the
CLI names the earliest identical one:

```text
Imported workflow <WORKFLOW_ID> revision 3 (identical to revision 1).
```

Reverting is therefore an import, and the revert itself is recorded.

The revision travels with what executes from it. Candidates, runs, production
state, experiment records and benchmark execution records name the revision
they used. Every such field is optional, so earlier records decode.

The CLI reads history with `history` (`workflow history`, `tool history`,
`benchmark history`) and prints any revision as an importable document with
`export`. `workflow revisions` keeps its meaning: production deployment
history (ADR 0064).

Databases written before revisions are migrated on open: each existing
artifact becomes revision 1, without an import time. Legacy tables are left
untouched.

## Consequences

### Positive

- Artifacts can change without losing history.
- Evidence names the exact content it judged.
- Reverts are explicit and visible.

### Negative

- Storage grows with every import, including identical re-imports.
- `history` (import history) and `revisions` (production history) are two
  words for two kinds of history, and must be kept distinct.

## Alternatives Considered

### Overwrite in place

Rejected. Evidence would point at content that no longer exists.

### Keep rejecting duplicate identifiers

Rejected. Artifacts could never be improved under their own identity.
