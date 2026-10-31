# ADR 0090: Loop by Invoking Child Workflows from a Tool

- Status: Accepted; amended by ADR 0093, ADR 0094
- Date: 2026-10-26
- Decided in: #104

## Context

A workflow is a directed acyclic graph. Each step runs at most once per run,
and dependency layers never revisit an earlier step.

Realistic work repeats, though. A novel is written chapter by chapter until
the story ends. An editor's requests are applied, checked, and applied again
until they are satisfied. A queue of edits is worked through one item at a
time. None of these has a length known when the workflow is written.

A loop construct in the engine would make the graph cyclic. Run records,
condition evaluation, name-only references, benchmarks and optimization all
assume each step produces its values once.

ADR 0084 already lets a parent run a child workflow as a separate process
through a tool.

## Decision

There is no loop construct in the engine. A loop is a tool that invokes a
child workflow repeatedly, through the same interface ADR 0084 uses:

```bash
azathoth workflow invoke <CHILD_WORKFLOW_ID> --input <JSON> --output jsonl
```

`examples/tools/loop-workflow.json` is the reference implementation. One
child invocation is one iteration, and state is carried between them as
plain JSON:

```text
loop input   {"workflow_id", "max_iterations", "state"?, "child_timeout_seconds"?}
child input  {"state": <state>, "iteration": <n>}
child result {"state": <next state>, "done": <bool>, "item"?: <value>}
loop result  {"items": [...], "state": <final state>, "iterations": <n>, "completed": <bool>}
```

The loop stops when the child reports `done`, or after `max_iterations`
calls. Running out of iterations is a result, with `completed` false, not a
failure. Each `item` a child returns is collected, in order.

The loop is bounded three ways:

- `max_iterations`, which the caller must set to a positive integer;
- a time budget inside the tool's own timeout, with each child stopped at
  `child_timeout_seconds` or the remaining budget, whichever is sooner, so no
  child outlives the loop;
- the child depth guard from ADR 0084, since loops may nest.

A failing iteration fails the loop and names the iteration, the child, and
the child's invocation ID:

```text
Iteration 2: child workflow <ID> invocation <INVOCATION_ID> failed: <MESSAGE>
```

A child that does not return a boolean `done` fails the loop the same way.

A loop that runs only some of the time is a conditioned step, with a
fallback producer declared after it in workflow step order (ADR 0080). Its
dependents read the value by name: the loop's value when it ran, because it
is declared first, and the fallback's when it was skipped. Declared order is
independent of dependencies, so the loop step may be declared before the step
that prepares it, and that step can produce the fallback.

## Consequences

### Positive

- The engine stays acyclic. Run records, conditions, references and
  optimization need no notion of iteration.
- Each iteration is its own invocation with its own run, so each can be
  inspected, benchmarked and optimized as an ordinary workflow.
- The loop body is promoted independently. Improving it improves every
  workflow that loops over it.
- Loops compose. The novel example nests a revision loop inside a chapter
  loop, three invocation levels deep.

### Negative

- Each iteration costs a process start and a production invocation.
- The whole loop must fit within one tool timeout. Long loops set a longer
  budget in their settings, within the tool's timeout (ADR 0093).
- Every iteration records its own invocation and run in the shared database,
  so long loops produce many records.
- The loop body must be promoted before the loop can use it.
- A parent names its child as a constant step input (ADR 0094). Before
  constants existed, a preparation tool held the child's ID as a default.

## Alternatives Considered

### A loop step type

Rejected. It would make the workflow graph cyclic, and every component that
assumes each step runs once would need to change.

### Unrolling a fixed number of steps

Rejected as the general mechanism. It is repetitive, fixes the iteration
count when the workflow is written, and leaves every unused copy in the
graph. It remains reasonable for one bounded pass, as the workflow-writer
example's single repair shows.

### Looping inside a Python tool

Rejected. Python tools run in process with restricted builtins (ADR 0078).
They cannot invoke workflows, and an in-process loop would hide each
iteration's evidence inside one step.
