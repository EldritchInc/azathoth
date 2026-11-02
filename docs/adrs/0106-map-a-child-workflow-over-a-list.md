# ADR 0106: Map a Child Workflow Over a List

- Status: Accepted
- Date: 2026-11-02
- Decided in: #124

## Context

A workflow is a directed acyclic graph, so a step runs once per run.
Repetition already lives in a tool: `loop_workflow` invokes a child once per
iteration, one after another, carrying state between them (ADR 0090). Much
work is not a loop, though. Counting the words of every chapter, reviewing
every file of a change, or classifying every ticket of a batch is the same
child applied to each item of a list, with no state between items, and it is
slow when done one at a time.

Composition is built from separate processes (ADR 0084). Every child records
its lineage (ADR 0104), and a child invoked under a key can be replayed or
resumed (ADR 0105). A fan-out should be built from the same parts, so that a
map stopped halfway resumes like any other run.

## Decision

### The tool

`map_workflow@1.0.0` joins the standard library beside `run_workflow` and
`loop_workflow`, with tool ID `c1000000-0000-4000-8000-000000000004` and
implementation `c1000000-0000-4000-8000-000000000044`. It grants itself the
same variables, and declares the same 24-hour timeout, as `loop_workflow`.

It invokes one deployed child once per item of `items`, at most
`max_concurrency` at a time, from a pool of threads in its own process:

| Setting | Default | Meaning |
| --- | --- | --- |
| `workflow_id` | required | The child to invoke for each item. |
| `max_items` | required | The most items the map accepts. |
| `max_concurrency` | 4 | How many children run at once, from 1 to 16. |
| `child_timeout_seconds` | 600 | How long one item's child may take. |
| `budget_seconds` | 7140 | How long the whole map may take (ADR 0093). |

Each child receives `{"item": <ITEM>, "index": <INDEX>}`, its index counted
from 0, mirroring the loop's `{"state", "iteration"}`. The map returns each
child's whole emitted result, as `run_workflow` does, in item order however
the children finish:

```json
{"results": [{"result": 4}, {"result": 2}], "count": 2}
```

A list longer than `max_items` is refused before any child runs. It is never
cut short: a workflow states the most it maps, as a loop states the most it
iterates. An empty list invokes nothing.

### Failures

Every item runs to its end, so one that fails never cancels another; the
items that finished stay reusable under their keys. The map then fails,
naming the first failing item by index, and how many failed:

```text
Item <INDEX> of <COUNT>: child workflow <WORKFLOW_ID> invocation <INVOCATION_ID> failed: <MESSAGE> (<FAILED> of <COUNT> items failed).
```

A child that outlasts `child_timeout_seconds` is stopped, and fails its
item. A map that outlasts its budget stops waiting, and leaves the children
still running to finish on their own runs, under their keys.

### Resuming

Each item's child is invoked under the key
`azathoth:<RUN_ID>:<STEP_ID>:<ATTEMPT>:<INDEX>` (ADR 0105). A resumed parent
re-runs its interrupted attempt under the same number, so every item finds
its key again: one that finished replays, one that stopped halfway resumes,
one another process still runs is waited for, and one that never started
runs. Every item runs once, and the results come back in order. An item that
failed replays its failure, so a resumed map fails as it would have.

A retried attempt has a new number, and runs every item again. Failures
replay under their key (ADR 0097), so reusing a failed item would make a
retry pointless.

### SQLite

The children of a map share one database. SQLite refused a transaction that
began deferred and then wrote, at once and without waiting, whenever another
process was writing, so children sharing a file failed each other. Every
SQLite transaction now begins immediately, taking the file's write lock, and
waits up to 30 seconds for another process's to commit.

## Consequences

### Positive

- The same child is applied to every item of a list, several at a time, as
  ordinary production invocations that can each be inspected, benchmarked
  and optimized.
- A map stopped halfway, by SIGTERM or by a killed process, resumes without
  paying for its finished items again.
- `run children` lists every item's run under the map, with no new index.
- Processes sharing one SQLite file take turns instead of failing.

### Negative

- Every item is a process with its own runtime, so a map of many tiny items
  spends more on starting processes than on the work.
- On SQLite, children write one at a time, so a wide map is bounded by the
  database rather than by `max_concurrency`. PostgreSQL has no such bound.
- Every SQLite transaction takes the write lock, so a read waits for a
  write in progress.
- A failing item fails the map. Collecting per-item errors instead, so a
  workflow can carry on past them, is left to a later decision.
- A retried map runs every item again, including those that succeeded.

## Alternatives Considered

### Fan out in the engine

Rejected. A step that runs many times would make the graph's runs, retries,
conditions and evidence depend on data, which is exactly what keeping
repetition in tools avoids (ADR 0090).

### Cancel the other items when one fails

Rejected. The items already running would be lost, and resuming the map
would run them again. Running every item to its end keeps each finished
item reusable.

### Truncate a list beyond its limit

Rejected. A map that silently dropped items would report a partial result as
a whole one.

### Collect only each child's `result`

Rejected. `run_workflow` returns the child's whole emitted result, and so
does the map, so any deployed workflow can be mapped unchanged, and
`json_select` picks out what a parent needs.

### Key items without the attempt

Rejected. A failed item would replay its failure on every retry of the step,
and a retry could never succeed.
