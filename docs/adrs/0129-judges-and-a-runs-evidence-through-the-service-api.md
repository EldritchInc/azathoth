# ADR 0129: Judges and a Run's Evidence Through the Service API

- Status: Accepted
- Date: 2026-11-18

## Context

The command line keeps the rotation of models that judge semantic cases
(ADR 0074) with `judge add`, `judge list` and `judge remove`. It records
whether a run was good or bad, why, and what it should have produced, with
`run feedback` (ADR 0068). It exports the verified citations a run's steps
kept as W3C Web Annotations with `run annotations` and `invocation
annotations` (ADRs 0113 and 0117), lists the runs a run's steps started
with `run children`, and continues an interrupted run from its journal with
`run resume` (ADR 0105).

None of these is in the service API (ADR 0120). The editor drives Azathoth
only through it, so it cannot keep the judges, take a person's judgment of
a run, show a run's citations or its children, or resume a run that
stopped. Each command also holds its own logic, beside the calls the API
already makes, so the two could come to disagree.

Nor can anyone find a run to resume without already knowing its ID.
`runs.list` and `run list` show finished runs only; a run that started and
never finished is in the journal, and nothing lists it.

## Decision

Every call here is an addition to the 1.x service API. The command line's
commands become thin wrappers over the same calls, as production's did
(ADR 0128), so there is one implementation of each. Each call is one of
the 0127 catalog's named actions, for a remote's policy in 1.6.

### `instance.judges`

| Call | Returns | Action |
| --- | --- | --- |
| `list()` | The rotation, in the order judges are tried | `read_catalog` |
| `add(identifier)` | The judge, appended to the rotation | `manage_judges` |
| `remove(identifier)` | The judge removed | `manage_judges` |

A `JudgeSummary` has the model's `identifier`, `provider` and `model`, its
`position` from 1, whether the portfolio still `authorized` it, and the
command that lists the rotation. Judges see benchmark data, so a judge must
be a model the providers serve now and the portfolio authorizes, as any
model a workflow may select (ADR 0074). Adding one that is not served is
`not_found`, one not authorized `model_not_authorized` (ADR 0128), and one
already in the rotation `conflict`. Removing one that is not a judge is
`not_found`; removing reads and writes durable state only, so it works
without provider credentials, for a judge whose model is gone too.

### Feedback

`runs.record_feedback(run_id, disposition, *, reason=None,
corrected_output=None)` records one immutable `good` or `bad` judgment of a
kept run and returns it as a `RunFeedback`: its ID, the run, the
disposition, the reason, the corrected output and when it was recorded.
`runs.feedback(run_id)` returns every judgment of a run, newest first.
Both are the `annotate_run` action, reading as well as writing, since
feedback is a person's annotation of a run.

A bad judgment needs a reason, and a corrected output contradicts a good
one, so it is accepted only with bad, as `run feedback` decides. A blank
reason is no reason. Each refusal is `invalid_argument` with the command
line's own message, and nothing is saved; a run that was never kept is
`not_found`.

`RunSummary` and `RunDetail` gain `feedback`, the run's latest disposition,
or `None` when it was never judged, as `run list` shows it.

### Annotations

`runs.annotations(run_id)` and `invocations.annotations(invocation_id)`
return an `Annotations`: the run's or invocation's ID, the run whose cited
steps kept the citations, the W3C Web Annotation collection exactly as the
command line prints it, its annotations in the order the steps checked
them, and the command that prints it. They are `read_runs`. The export
moves from the command line into the API; `run annotations` and
`invocation annotations` print what it returns, so the JSON is the same
either way.

A run that was neither kept nor journaled, an unknown invocation and one
with no run yet are `not_found`. A record of checks the content store no
longer holds, or holds something else under, raises a second new error,
`ContentUnavailableError`, code `content_unavailable`.

### Child runs

`runs.children(run_id)` returns the runs a run's steps started, oldest
first, each a `RunChildSummary`: the child run and its workflow, the
invocation it executed when it executed one, the step and attempt of the
parent that started it, and its `status`, `succeeded`, `failed`, or
`unfinished` while no finished run is kept for it, with the command that
shows it once there is one. It works for a parent that never finished,
since a child is indexed as it starts, and refuses a run that was neither
kept nor journaled as `not_found`. It is `read_runs`.

### Resuming a run, and finding one to resume

`runs.interrupted(workflow_id)` lists a workflow's runs that started and
never finished, newest first, each an `InterruptedRun`: its ID, workflow
and revision, when it started, how often it was resumed, the invocation it
executes when it executes one, and the command that resumes it. It is
`read_runs`. `azathoth run interrupted WORKFLOW_ID` prints the same list,
so the command line can find what it resumes too.

`runs.resume(run_id, *, on_event=None, cancel=None)` continues an
interrupted configured run from its journal, reporting its events as
`runs.run` does, and returns its `RunResult`. It is `run_workflow`. A run
that executes an invocation is resumed as its invocation, by
`invocations.resume` (ADR 0128), so production records its outcome;
`runs.resume` refuses it, naming the call that resumes it.

The other new error, `RunNotResumableError`, code `run_not_resumable`, refuses a
run that has finished, one executing an invocation, and one whose journal
cannot be resumed, with the messages `run resume` gives. A run that was
never journaled is `not_found`.

## Consequences

- The editor can keep the judges, take and show a person's judgment of a
  run, show its citations and its children, and find and resume a run that
  stopped, through the service API alone.
- The command line and the API cannot disagree about feedback, annotations,
  children or resuming, since the command line calls the API.
- A run that stopped is findable from its workflow, by the command line as
  well as the editor, without knowing its ID first.
- A remote in 1.6 decides each of these by the action it is.

## Alternatives Considered

### Listing interrupted runs in `runs.list`

`runs.list` returns `RunSummary`s, which describe how a run ended; an
interrupted run has not ended, so every field about its outcome would be
empty, and every caller of `runs.list` would have to tell the two apart. A
call of its own says what the run is.

### Feedback as an editable record

Letting a judgment be changed would lose why a run was first judged as it
was. Judgments stay immutable, as ADR 0068 decided; a new judgment is a new
record, and the latest is the run's disposition.

### Resuming an invocation's run with `runs.resume`

Resuming the run alone would leave its invocation incomplete, though its
run finished. Resuming it as its invocation records the outcome production
callers read.
