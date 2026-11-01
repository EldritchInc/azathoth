# ADR 0084: Run Child Workflows as Separate Processes

- Status: Accepted; amended by ADR 0090, ADR 0099
- Date: 2026-10-25
- Decided in: #101, #103

## Context

Composing workflows out of other workflows is central to letting domain
experts build on each other's work. A child workflow needs its own lifecycle,
though: its own benchmarks, optimization, promotion and production history.

A dedicated "run workflow" step type would pull the child's execution into
the parent's run, couple their evidence, and require the runner to handle
nested lifecycles.

## Decision

There is no child-workflow step type. A parent runs a child as a separate
process, through a tool, using the same interface every external caller uses:

```bash
azathoth workflow invoke <CHILD_WORKFLOW_ID> --input <JSON> --output jsonl
```

The child is invoked, so it runs its promoted production state and records its
own invocation and run.

The parent sees only the child's result. The child's step records stay in the
child's own evidence.

`examples/tools/run-workflow.json` is the reference implementation: a process
tool (ADR 0078) that runs the child with its own interpreter
(`python -m azathoth.cli`), keeps only the final JSON Lines record, and
reports a failure with the child's invocation ID so an operator can follow it
with `invocation show` and `run show`. The child inherits the parent's
environment, and so its database.

Child depth is bounded by the example tool itself. It passes
`AZATHOTH_WORKFLOW_DEPTH` to each child and refuses beyond 8 levels, and it
stops a child before its own timeout so that no child outlives it.

Deferred until after 1.0:

- recording lineage and depth in the child's initial context, so the engine
  rather than a tool bounds depth;
- constant step inputs, so that a parent can name its child in its own
  specification instead of receiving the child's ID as input.

## Consequences

### Positive

- Children keep their own lifecycle and evidence.
- Composition uses the public CLI, not an internal mechanism.
- The runner needs no knowledge of nesting.

### Negative

- Each child call costs a process start.
- Until lineage is recorded, the link from a parent run to its child
  invocation exists only in the tool's output.
- Until constant inputs exist, the caller names the child.

## Alternatives Considered

### A dedicated child-workflow step type

Rejected. It would merge two lifecycles into one run.

### Run children with `workflow run`

Rejected. A parent would depend on whatever happens to be configured, not on
what was deliberately promoted.
