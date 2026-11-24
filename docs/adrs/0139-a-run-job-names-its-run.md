# ADR 0139: A Run Job Names Its Run

- Status: Accepted
- Date: 2026-11-23

## Context

ADR 0138 runs `runs.run` on a remote as a job. A run is journaled as it
goes, but its ID was made inside the run, and known only once the call
returned. A job whose server stopped mid-run could not name the run to
resume it, so ADR 0138 interrupted it, and told its caller to find the run
with `runs.interrupted` and resume it themselves. Every other job a
journal could carry on, a resumed run or an invocation, went on by itself.

ADR 0138 took a runner to have stopped once it had not beaten in 60
seconds. A run's lease (ADR 0105) also lasts 60 seconds, so a runner taken
for stopped could still hold the lease of the run it was running; whoever
resumed it next would be refused the lease, and a job resumed too early
would fail where waiting a little longer would have let it go on.

A job's events are streamed from the database, and the stream ends once
it reads that the job has finished. A runner keeps a job's last event and
then finishes the job, and the stream could read the two in between: it
read the events, the runner kept one more and finished the job, and the
stream, now reading the job as finished, ended without the last event. A
run's `invocation_finished`, the event a caller waits for, was lost this
way.

## Decision

### A run is named before it starts

`runs.run` makes the run's ID before the run starts, and runs the run
under it. `RunStarted` gains `run_id`: the new run of `runs.run`, or the
run `runs.resume` goes on with. An invocation's run is named through its
invocation, so `run_id` is None for one. `WorkflowRunner.run` and
`run_recording_failures` take the `run_id` to run under, and so does the
tracing runner that wraps them.

### A run job left by a stopped server is resumed

A runner keeps the run a `runs.run` job names as its `RunStarted` is told.
A run job a stopped server left is queued again with the others, and,
when it is started again, resumes the run it named, from its journal, as
`runs.resume` would. A run that journaled nothing before its server
stopped is not found, so it runs as it was submitted, since none of it ran.

`runs.run` is among the calls queued again rather than interrupted, with
`runs.resume`, `invocations.resume` and `runs.invoke`, and nothing says to
find an interrupted run any longer. Interrupted, refused 409 `interrupted`,
are only the calls nothing resumes: a benchmark run, a comparison, an
optimization and a step tried.

### A runner is taken for stopped after 90 seconds

A runner that has not beaten in 90 seconds is taken to have stopped: a
run's lease, 60 seconds, and three beats more, at 10 seconds each. A run
its runner held has been let go before another runner resumes it, and a
runner `/v1/service` counts alive, having beaten in the last 60 seconds,
is never taken for stopped.

### A stream reads a job's events once more when it ends

A stream that reads that its job has finished reads the job's events once
more, and sends any it had not, before it sends the job's `finished`
event. A runner always keeps a job's last event before it finishes the
job, so that last read finds every event.

## Consequences

- Every `runs.run`, `runs.resume`, `runs.invoke` and `invocations.resume`
  through a remote outlives the server that ran it, and goes on from its
  journal.
- A job left by a server that stopped without handing it back waits up to
  90 seconds, rather than 60, before another runner takes it.
- `RunStarted` names its run, so a caller following a run on a remote
  knows the run's ID from the first event, not from the result.
- A caller following a job's events receives every one of them, in order,
  before `finished`.
- A local run tells its ID in `RunStarted` too, so a callback here and one
  on a remote see the same events.

## Alternatives Considered

### Naming the run in the job's result

A run's ID in its result arrives only once the run has finished, which is
what a server that stops never reaches.

### A shorter lease

Shortening a run's lease to expire inside 60 seconds would change every
run's lease, wherever it runs, to fit one way of running jobs. Waiting
three beats longer to recover a job costs a caller at most half a minute,
once, when a server stops.

### Ending the stream on the runner's last event

A stream told by the runner which event is last would need a mark that
every call's events carry. Reading once more after the job has finished
needs nothing new, since the runner already keeps the last event first.
