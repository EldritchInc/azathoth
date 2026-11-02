# ADR 0104: Record Lineage in a Child's Initial Context

- Status: Accepted
- Date: 2026-11-01
- Decided in: #122

## Context

A parent runs a child workflow as a separate process, through a tool that
runs `azathoth workflow invoke` (ADR 0084), and a loop does the same once per
iteration (ADR 0090). The engine knew nothing about this nesting:

- The only link from a parent run to its child invocation was the tool's
  output. Given a child, nothing recorded which run, or which step of it,
  started it. ADR 0084 named this a cost and deferred recording lineage.
- Depth was bounded by the composition tools themselves. Each read
  `AZATHOTH_WORKFLOW_DEPTH`, added one, refused beyond 8, and passed the new
  value to its child. A tool that did not, such as an operator's own tool
  that runs `azathoth`, could nest without limit, and every tool that did had
  to grant itself the variable (ADR 0099).
- A run's ID was assigned only when the run finished, so a step could not
  name the run it belonged to.

Resume (ADR 0105), `map_workflow` (ADR 0106) and the queue worker (ADR 0107)
all need to know where a run came from.

## Decision

### The lineage a child records

A run started by a step of another run is that step's child. Its initial
context records one `workflow.lineage.received` event, produced by
`azathoth.lineage`, after its input events:

```json
{
  "depth": 1,
  "parent": {"workflow_id": "<ID>", "run_id": "<ID>", "step_id": "<ID>", "attempt": 1},
  "root": {"workflow_id": "<ID>", "run_id": "<ID>"}
}
```

- `depth` counts the levels below the root: a child of a root run is at 1.
- `parent` is the attempt of the step that started the run. `attempt` tells
  apart the children of a retried tool call.
- `root` is the run at the top of the tree.

Lineage is keyed by runs, not invocations. The runner does not know whether
it executes an invocation, and a parent invocation is reachable from its run
through the invocation's run association.

A run started from outside Azathoth records no lineage event. It is a root,
at depth 0, and records exactly the context it always did, so no existing
run, benchmark case or content digest changes.

The model lives in `azathoth.context`: `WorkflowLineage`, `LineageRun`,
`LineageStep`, `RunLineage` and `StepLineage`, with `lineage_of`,
`run_lineage`, `child_lineage` and `create_lineage_event`. A context records
lineage at most once; a second event, or one that is not valid lineage,
raises `LineageError`.

### How lineage reaches a child

The runner assigns a run's ID when the run starts, and the recorded
`WorkflowRun` keeps it. It reads the run's own lineage from the initial
context before any step executes; lineage that is not valid stops the run.
While each step attempt executes, the attempt's `StepLineage` is current, in
a context variable that follows the step's task, threads included.

A process tool run inside a step receives that lineage as compact JSON in
`AZATHOTH_LINEAGE`. It is managed by the engine, beside the timeout and the
trace context (ADR 0093, ADR 0100):

- it cannot be granted;
- a copy in Azathoth's own environment never reaches a tool, so a child
  `azathoth`, which receives its parent's this way, hands its own steps'
  lineage to its tools, never the one it inherited.

`workflow run`, `workflow invoke` and `job run` read `AZATHOTH_LINEAGE` and
record the child's lineage, one level below the step's run, in the initial
context of the run or invocation they start. Without the variable, or with it
empty, they start a root. A tool that runs `azathoth` needs no change and no
grant to take part.

### The engine bounds depth

`MAX_WORKFLOW_DEPTH` is 8, the limit the tools enforced. A child that would
run deeper is refused before anything is resolved or recorded: no input file
is stored, and no invocation or run is saved. So is lineage that is not
valid. The command prints one line on stderr, writes nothing on stdout, and
exits with status 1, as it does for other failures found before anything is
recorded; `job run` prints no envelope:

```text
Workflow <WORKFLOW_ID> would run at depth 9, beyond the limit of 8 nested workflows.
AZATHOTH_LINEAGE is not valid lineage: step: Field required.
```

The tool that started the child reports that line as its step's failure.

### Inspection

`invocation show` and `run show` name a child's depth, parent workflow, run,
step and attempt, and root workflow and run. A root shows no lineage.

### The composition tools

`run_workflow` and `loop_workflow` no longer count depth. They ship as the
next revisions of the same versions, implementations 1.0.4 and 1.1.4, as the
earlier 1.1 grant changes did (ADR 0099): they drop the counter and the
`AZATHOTH_WORKFLOW_DEPTH` grant, and write their errors as UTF-8 on every
platform. Implementations 1.0.3 and 1.1.3 still run: they count depth
themselves, and the engine's limit applies to their children too. The engine
never reads `AZATHOTH_WORKFLOW_DEPTH`.

## Consequences

### Positive

- Every child names the run and step that started it, and the root of its
  tree, in its own recorded evidence.
- Nesting is bounded for every tool that runs `azathoth`, not only the
  standard ones, and no tool grants itself a depth variable.
- A child workflow can bind its lineage like any other context value.
- No schema changes: lineage rides inside the recorded initial context, in
  SQLite and PostgreSQL alike.

### Negative

- A parent run that is killed, for example when its tool step times out, is
  never recorded, so its children's `parent.run_id` names a run that does not
  exist. Recording runs as they progress belongs to resume (ADR 0105).
- Finding a run's children means reading every invocation's initial context.
  An index of parents and children, which resume also needs, means a schema
  version 2 and is left to ADR 0105.
- A loop's iteration number is not part of lineage. The child receives it in
  its input; resume decides what mid-loop resume needs.
- `AZATHOTH_LINEAGE` set by hand in a shell is honored like any other.
  Lineage is evidence the engine records, not a security boundary.

## Alternatives Considered

### A `--parent` flag on the run-starting commands

Rejected. Every tool would have to read its step's lineage and remember to
pass it, and a tool that forgot would escape the depth limit. A managed
variable reaches every child, as the trace context does.

### Key lineage by invocation

Rejected. The runner does not know its invocation, and runs that are not
invocations, such as `workflow run` and benchmark cases, could not be
parents.

### Record refused children as failed invocations

Rejected. It would add an error code to the invocation and job-result
contracts, and record an invocation that never ran. A refused child leaves
no evidence; its parent's failed step records why.

### Keep the depth limit in the tools

Rejected. The engine is the only place that sees every child, and a limit
each tool must reimplement is a limit some tool will not.
