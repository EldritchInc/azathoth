# ADR 0105: Resume Interrupted Runs From a Journal

- Status: Accepted
- Date: 2026-11-01
- Decided in: #123

## Context

A run was recorded only when it finished. A process that died halfway, from
a deploy, a crash, a lost container or Ctrl-C, left nothing behind but the
invocation it was executing, and that invocation stayed without a result for
ever:

- `job run` reported it `incomplete` under its key, and nothing could finish
  it (ADR 0097).
- A parent killed while its tool step ran left children whose
  `parent.run_id` named a run that never existed (ADR 0104).
- A loop that died at its fortieth iteration started again from the first,
  and paid for every child again (ADR 0090).

The queue worker (ADR 0107) will run invocations on machines that come and
go, so an interrupted run must be the ordinary case, not the lost one.

## Decision

### Scope

Production invocations, started by `workflow invoke` or `job run`, and
configured runs, started by `workflow run`, can be resumed. Benchmark cases
and optimization runs cannot: they are evaluated as a whole, and a case
interrupted is simply run again.

### The journal

A runner given a journal records each run as it executes, in an append-only
journal numbered from 1, beside the recorded `WorkflowRun`, whose shape does
not change:

| Entry | Recorded |
| --- | --- |
| `run.started` | The workflow, its revision and the initial context. |
| `attempt.started` | Before each attempt of a step executes. |
| `attempt.finished` | After each attempt, with the whole `WorkflowStepAttempt`. |
| `layer.committed` | A layer's step runs, the events it added to the context, and the steps blocked so far. |
| `run.resumed` | Each time a process resumes the run. |
| `run.finished` | When the run ended, and whether and where it halted. |

Every entry names the run, its workflow, and the invocation it executes. The
journal of a finished run holds the whole run, so a process that died after
the run finished but before it was recorded loses nothing.

Each entry is recorded outside the attempt it describes. An entry that
cannot be recorded never fails or retries a step: it stops the run at once,
with its error, and the run stays unfinished. A production invocation whose
run stops that way records no result.

### Schema version 2

The journal, the leases and the index of children are three new tables:
`run_journal`, `run_leases` and `run_children`. They are schema version 2,
which only adds tables. `azathoth init` upgrades a PostgreSQL database of
version 1 in place, under its advisory lock, and every other command refuses
one until it has (ADR 0102). An SQLite file gains the tables when they are
first used.

### Leases

A process holds a lease on each run it executes, acquired before the run's
first entry. It lasts 60 seconds and is renewed every 15, from a thread of
its own; transactions on PostgreSQL's one connection take turns across
threads. The lease is released when the run ends, however it ends, so a run
stopped by Ctrl-C or SIGTERM can be resumed at once. A process killed
outright leaves a lease that lapses within a minute.

Only one process executes a run. A live lease refuses another:

```text
Run <RUN_ID> is still running (its lease expires at <TIME>).
```

The lease is the journal's fence. A process whose lease was taken over, or
lapsed before it could be renewed, writes nothing more to the run's journal,
and two writers of one run collide at the first position they share.

`workflow run`, `workflow invoke` and `job run` exit with 130 on Ctrl-C and
with 143 on SIGTERM, printing `Interrupted.` or `Terminated.`, after the run
has released its lease. The queue worker's own shutdown is ADR 0107's.

### Resuming

A run resumes under its own ID, with its initial context, its start and its
invocation, from the workflow it started from:

- every layer it committed is reused as it was, and the events it added are
  replayed into the context;
- in the layer it was executing, a step whose last finished attempt
  succeeded is reused, with the context that attempt ran in; one whose
  attempts failed retries from its next attempt number; one with no attempts
  left fails as recorded;
- an attempt that started but never finished runs again, under the same
  number. Work in flight when the run stopped runs at least once, and may
  run twice.

A configured run resumes from the specification revision it started from.
An invocation resumes from the production state that was active when it was
created: the last production revision no later than the invocation, or the
state active now for a workflow promoted before revisions were recorded. The
revision the run's journal records must match; a newer import or promotion
never changes a run halfway. Inputs come from the recorded initial context,
so nothing is resolved again.

A run that cannot be resumed with the workflow is refused with what does not
match, and nothing runs. The invocation stays incomplete.

### Commands

```bash
azathoth run resume <RUN_ID>
azathoth invocation resume <INVOCATION_ID>
```

Each reports the finished run exactly as the command that started it would
have. `run show` says how to resume a run that never finished, and names how
often a finished run was resumed. `job run` resumes an incomplete invocation
under its key once no process holds its run, and reports its result with
`replayed: false`; one still held is `incomplete`, as before.

### Children under keys

`workflow invoke` takes `--idempotency-key`, and then runs exactly as
`job run` does under that key (ADR 0097): the same request replays, or
resumes; another request is a conflict.

The standard composition tools invoke every child under the key of the step
attempt that starts it, `azathoth:<RUN_ID>:<STEP_ID>:<ATTEMPT>`, and a loop
under one key per iteration, with `:<ITERATION>` appended. They ship as the
next revisions of the same versions, `run_workflow` 1.0.5 and `loop_workflow`
1.1.5, as the earlier 1.1 changes did (ADR 0099). A resumed parent re-runs
its interrupted attempt under the same number, so the tool reuses the
children that attempt already ran: a loop resumed halfway replays its
finished iterations, resumes the one it was running, and runs the rest. A
child another process still runs is waited for, until the tool's timeout. A
retried attempt has a new number, and runs its children again.

### The index of children

A run started with lineage indexes itself under the run, step and attempt
that started it, as it starts, once. `run children <RUN_ID>` lists a run's
children with their status, even for a parent that never finished, and
`run show` names how many children a run started.

## Consequences

### Positive

- An interrupted invocation or configured run is finished, not lost, under
  the IDs its callers already know.
- A loop or a tree of children resumed halfway pays only for the work it had
  not done.
- A retried job finishes the invocation its key started, instead of
  reporting it incomplete for ever.
- A parent finds its children, and every child's parent run exists in the
  journal from its first entry.
- Two processes never execute one run at once.

### Negative

- A run writes a journal entry per attempt and per layer, holding each
  attempt's whole execution, so a finished run's evidence is stored about
  twice: once in its journal, once as the `WorkflowRun`. Retention is a
  separate decision.
- Work in flight when a run stopped runs again. A step whose tool has side
  effects outside Azathoth may repeat them; only children invoked under keys
  are reused.
- A process killed outright holds its runs for up to a minute before they
  can be resumed.
- PostgreSQL needs `azathoth init` once after upgrading.
- A retried attempt still runs its children again: keys reuse the children
  of one attempt, not of the step.

## Alternatives Considered

### Checkpoint the whole context after each layer

Rejected. It cannot resume inside a layer, so an interrupted layer with one
finished long step would run that step again, and every checkpoint would
copy the whole context.

### Rebuild progress from the children's invocations

Rejected. Only composition steps have children; a model step's attempts would
be lost, and so would every step that is not a child.

### Mint new run IDs on resume

Rejected. Callers, children and traces already name the run; a resumed run
that changed its ID would orphan its children and break `run show`.

### Resume benchmark and optimization runs too

Rejected for now. Their results are judged as a whole, so a case run again
from the start costs only the case, and resuming one would need its own
evidence rules.

### Keep leases in the journal

Rejected. A lease changes every 15 seconds while a run is quiet; a journal
entry per renewal would bury the run's real progress.
