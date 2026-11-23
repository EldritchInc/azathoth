# ADR 0138: Jobs on a Remote

- Status: Accepted
- Date: 2026-11-23

## Context

Eight calls of the service API take a callback for their events:
`runs.run`, `runs.try_step`, `runs.invoke`, `runs.resume`,
`invocations.resume`, `benchmarks.run`, `benchmarks.compare` and
`optimization.optimize`. They run for minutes, and what they tell along
the way is how the command line and the editor show a run as it goes.

ADR 0127 decided that a remote runs them as jobs, queued as ADR 0107
queues a job and run by the remote's workers, with their events streamed
back. ADR 0136 served every other call and answered these 501 `job`, and
ADR 0137's client refused them before sending anything. Neither said what
a job is on a remote, where it waits, who runs it, who may watch or stop
it, or what becomes of it when the server running it stops.

ADR 0107's worker reads a versioned job request from SQS and answers on
another queue. It runs one kind of job, a production invocation, needs
AWS, and keeps no events. A remote is served by `azathoth remote serve`
on any machine, over SQLite or PostgreSQL, and every one of the eight
calls has to run there as its caller, with every event kept for whoever
follows it.

## Decision

### A remote keeps its jobs in its database

Schema version 8 adds three tables. `service_jobs` holds each job: its
call, its caller, its arguments as the call's signature writes them, the
resource the policy was asked about, its status, when it was submitted,
started and finished, the runner holding it and when that runner last
beat, who asked it to stop and when, the run it started, how many times it
was started, and its result or its refusal with the status it is refused
with. Jobs are taken in the order they were submitted. `service_job_events`
holds each event a job told, numbered from 1 in the order told.
`service_job_runners` holds each runner, the host it runs on, and when it
last beat.

A job is `queued`, `running`, or finished as `succeeded`, `failed`,
`cancelled` or `interrupted`.

### A remote's server runs them

`azathoth remote serve` runs jobs on threads of its own process:
`JobRunners` starts `--jobs` runners, 2 by default. Each runner takes the
job waiting longest and runs its call through its caller's own instance,
as ADR 0136 answers a call, so what it makes is recorded as the caller's.
Each event the call tells is kept before the next. A call's result is kept
as its signature writes it; an `ApiError` is kept as the refusal a route
would have answered, and a cancelled call as `cancelled`; anything else is kept as a failure whose message
says to read the remote's log:

```text
<CALL> failed at the remote; its log says why.
```

`--jobs 0` runs none and still accepts them, for another server over the
same PostgreSQL database to run. A runner takes a job inside a transaction
that holds `service_jobs`' write lock, so two runners, on one server or on
several, never take the same job.

One more thread watches the runners. Each second it asks a running job to
stop once a caller has asked that of it, and every 10 seconds it beats for
every runner, recording that it is alive. A runner that has not beaten in
60 seconds is taken to have stopped, and its jobs are recovered, by
whichever server notices first.

### A job a stopped server leaves is resumed where it can be

A recovered job that can go on from where it was is queued again, and is
started once more, as its next attempt. A resumed run resumes again; a
resumed invocation, or an invocation, is invoked again under its
idempotency key, which resumes it from its journal. Every invocation
submitted as a job is given a key, `job-<JOB_ID>`, when its caller gives
none, so this holds for every one.

Any other job is finished as `interrupted`, refused 409 with the code
`interrupted`, since nothing resumes a benchmark run, a comparison, an
optimization or a step tried:

```text
The server running this job stopped before it finished, and nothing resumes <CALL>; submit it again.
```

A run started by `runs.run` is journaled, but its ID is known only once
the call returns, so the job cannot name it to resume it. It is
interrupted saying where to find it:

```text
The server running this job stopped before it finished. A run it started is named by runs.interrupted, and runs.resume resumes it from its journal.
```

A server that stops hands back the jobs it was running at once, asking
each to stop and recovering it as above, rather than waiting 60 seconds.

### A job is submitted as its call is made

A job is `POST /v1/calls/<NAME>`, as every call is. The remote reads its
arguments by the call's signature, asks the policy its actions and
conditions, and tells its audit before queueing it, exactly as it would
before running the call. It then answers 202 with a `JobAccepted`: the
job's ID, its call, its status, when it was submitted, and the paths of the
job and of its events, the job's path also in `Location`.

A remote built with nowhere to keep jobs, as a plugin may build one,
refuses a job 501 with the code `job`, and its job routes 404:

```text
<NAME> runs as a job on a remote's runners, and this remote runs none.
This remote runs no jobs.
```

### Who may read and stop a job

| Route | Answers |
| --- | --- |
| `GET /v1/jobs` | the caller's own jobs, newest first, 100 by default and up to 1000 with `?limit=` |
| `GET /v1/jobs/{job_id}` | the `JobView`: the job, and its result or refusal once it has finished |
| `POST /v1/jobs/{job_id}/cancel` | the `JobSummary`, once the job is asked to stop |
| `GET /v1/jobs/{job_id}/events` | the job's events as server-sent events, then the `JobView` it ended as |

The caller who submitted a job may read it, follow it and stop it. Another
caller is asked `read_runs` to read or follow it, and the actions of its
call, such as `run_workflow`, to stop it, each about the job as `job
<JOB_ID>`. A listing is only ever the caller's own jobs.

A job's result or events are sent only once it is decided whether they are
restricted. A run, a step tried or an invocation is restricted by the
label it was submitted with, a resume by the run or invocation it resumes,
and a benchmark run, a comparison or an optimization by its benchmark. For
a restricted job, the policy is asked `read_restricted` about it, and the
audit told `restricted_read`, before anything is sent.

Stopping a job tells the audit the new kind `job_cancelled` first, naming
the job's call; it records no action of its own. A queued job is cancelled
at once. A running one is asked to stop, and stops as the call stops for
a cancelled token, within a second.

### A job's events are server-sent events

`GET /v1/jobs/{job_id}/events` answers `text/event-stream`. Each event the
job told is sent as one event named `event`, its ID its number and its
data the `RunEvent`, `BenchmarkEvent` or `OptimizationEvent` as JSON, exactly
as `on_event` receives it locally. Once the job has finished, one more
event named `finished` carries its `JobView`, and the stream ends. A
client that reconnects with `Last-Event-ID`, or `?after=`, is sent only
the events after that number, so none is missed and none sent twice. A
stream quiet for 15 seconds sends a comment, `: still running`, so neither
side takes it for lost. The events are read from the database, so any
server over it streams the events of a job any other runs.

### A remote says how its jobs stand

`GET /v1/service` gains `jobs`: how many jobs wait, how many run, when the
oldest waiting was submitted, and how many runners have beaten in the last
60 seconds. A remote that runs no jobs gives none. A client warns that a
job will wait from it.

### A connected instance calls a job as a local one

`ConnectedInstance` calls each of the eight as the local instance does,
with the same arguments and the same result. It submits the job, follows
its events, hands each to `on_event`, and returns the result the job ended
with, or raises its refusal as the error the local call would have
raised. A callback that raises is told no more events, and the job goes
on. Once the call's `cancel` is cancelled, the client asks the remote to
stop the job, and raises `RunCancelledError` when it has stopped. A token
cancelled before the call sends nothing.

A stream that drops is followed again from the last event seen, up to 5
more times, waiting a little longer each time. After that the client gives
up following it and says the job goes on:

```text
The remote at <URL> dropped the events of job <JOB_ID> 6 times, so they are no longer followed; the job goes on there, and jobs.get finds it.
```

A connected instance's `jobs` reaches jobs apart from their calls: `submit` queues one
and returns its `JobAccepted` without waiting, `follow` waits for one,
handing on its events, and returns its result, `get` and `list` read
them, and `cancel` asks one to stop. A local instance has no `jobs`,
since it runs nothing but what it is asked to while it is asked.

`azathoth.remote.sse.read_server_sent` reads a stream's lines into its
events, as a browser would, and needs no web framework.

## Consequences

- Every call of the service API runs on a remote. A run started through a
  remote outlives the request that started it, the client that follows it
  and, when it can be resumed, the server that ran it.
- A job's events and result are kept in the database as long as the job
  is. Nothing yet removes finished jobs, so a busy remote's job tables
  grow until a later release prunes them.
- A job left by a server that stopped without handing it back waits up to
  60 seconds before another runner takes it.
- `runs.run` through a remote is interrupted, not resumed, when its server
  stops. Resuming it needs the run's ID from the moment it starts, which
  a later decision may add to the events a run tells.
- SQLite serves one remote process, so on SQLite `--jobs 0` leaves jobs
  queued until the server is started again with runners. It is for
  several servers over one PostgreSQL database.
- A remote's runners call model providers with the keys the server read
  when it started, as every call through it does.
- ADR 0107's SQS worker is unchanged: it runs production invocations from
  a queue, as `azathoth job run` does, and is not how a remote runs its
  jobs.
- The database schema moves from version 7 to version 8. An SQLite file
  is upgraded the first time it is used; a PostgreSQL database by `azathoth
  init`, after which an older Azathoth refuses it.

## Alternatives Considered

### Running jobs on the SQS worker

ADR 0127 named ADR 0107's workers. They need AWS, run one kind of job, and
keep no events, so a remote on one machine, or on PostgreSQL elsewhere,
could run none of the eight. Runners in the server need nothing the
remote does not already have, and several servers over PostgreSQL share
the work as several workers would.

### Running a job while its request waits

A job answered inside its request would hold a connection and a thread
for as long as it ran, and would end, events and all, with a dropped
connection. A queued job survives both, and a client that reconnects is
sent only what it missed.

### Polling for events instead of streaming them

A client polling `GET /v1/jobs/{job_id}` would see events late, or ask
many times a second. Server-sent events are one request a client keeps
open, carry IDs a client reconnects from, and pass through the proxies and
load balancers that pass HTTP. WebSockets would add a second protocol for
traffic that only ever goes one way.

### Claiming with `FOR UPDATE SKIP LOCKED`

On PostgreSQL, `SKIP LOCKED` lets two runners claim different jobs at the
same moment. SQLite has no such clause, and a claim is one short
statement, so holding the table's write lock while it runs costs little
and is the same on both databases.
