# ADR 0107: Run Jobs From a Queue

- Status: Accepted; amended by ADR 0108, ADR 0109
- Date: 2026-11-02
- Decided in: #125

## Context

Azathoth 1.1 runs on AWS behind a queue. Programs send it job requests
(ADR 0097), and containers from one image (ADR 0101), sharing one PostgreSQL
database (ADR 0102), run them. The pieces a queue needs already exist: a job
request carries its own idempotency key, so a request delivered twice runs
once, and a run interrupted halfway resumes from its journal, under a lease
only one process holds at a time (ADR 0105).

What was missing was the process that takes requests from the queue. Amazon
SQS delivers each message at least once. A received message is hidden for a
visibility timeout, and delivered again once that runs out, unless it was
deleted. ECS stops a task with SIGTERM, and kills it outright once its stop
timeout passes. Earlier decisions left several questions to this one: how
the worker stops (ADR 0105), how its health is checked (ADR 0101), whether it
pools connections (ADR 0102), and which inputs it accepts (ADR 0096).

## Decision

### The command

`azathoth worker run --queue-url <URL>` takes job requests from one SQS
queue and runs them, one at a time, until it is stopped. Each message's body
is exactly one job request, and it is answered as `job run` answers it: a key
seen before replays, an interrupted invocation resumes, and anything else
runs.

The loop lives in `azathoth.worker`, behind a `JobQueue` protocol, and the
SQS queues behind it use boto3, in a new `worker` extra the image installs.
boto3 is imported only when a queue is opened.

### Settling a message

The job's result settles its message:

| Result | Message |
| --- | --- |
| `succeeded` | Sent to the result queue, when there is one, then deleted. |
| `failed` | Sent to the result queue, when there is one, then deleted. |
| `rejected` | Sent to the result queue, when there is one, then deleted. |
| `incomplete` | Left, to come back when its visibility timeout runs out. |

A final result is never lost by deleting first: it is sent, then its message
deleted, so a worker that dies in between sends it again as a replay.

`incomplete` means another process holds the run's lease. Leaving the message
lets the visibility timeout space out the retries, and once the lease lapses
the next receipt resumes the run. A worker that dies mid-run leaves its
message the same way.

### Visibility

A received message is hidden for `--visibility-timeout-seconds`, 120 by
default, and hidden again every `--extend-every-seconds`, 30, while its job
runs, so it is not delivered again under a live run. A lease lapses within
a minute (ADR 0105), so a dead worker's message comes back after about two,
and finds its lease already lapsed. An extension SQS refuses is reported,
and the job carries on: the lease, not the visibility timeout, is what keeps
two workers from running one run.

### Results

`--result-queue-url` names a standard SQS queue that every final result is
sent to, as the line `job run` prints, with the request's key in the
`idempotency_key` attribute. It is optional: every result is recorded in the
database, and the same request sent again replays it. A FIFO result queue is
refused. The job queue may be either.

### Poison messages

A request that does not decode is `rejected`, sent and deleted, never
received again. A message that keeps stopping workers, as one that kills the
process would, is the queue's to move aside with a dead-letter queue. The
worker does not count receipts.

### One job at a time

A worker runs one job at a time, and a deployment scales by running more
workers. Each process then keeps the single connection a `PostgresDatabase`
holds, and needs no pool: the children of a map are processes of their own,
with connections of their own. Running several jobs in one worker, and a pool
to serve them, wait for a workload that needs them.

### Stopping

The first Ctrl-C or SIGTERM drains the worker. It prints `Stopping.`, lets a
receive in progress finish, and cancels the job running, which releases its
run's lease as it unwinds. It then makes the message visible at once, so
another worker resumes the run from its journal instead of waiting out the
timeout. A message received as the stop arrives is handed back unrun. The
worker prints `Stopped.` and exits with 0: a worker told to stop that
stopped cleanly has not failed.

A second signal stops it where it is, with 130 or 143, as other commands
exit (ADR 0105). Its message comes back when its visibility timeout runs
out.

A drain takes at most one receive wait, 20 seconds, and a job's unwinding,
so a task's stop timeout should be longer: 60 seconds.

### Failures of the worker

A handler never raises for a request's own problems; those are results. A
queue that refuses a call, or a job that cannot run at all, as when the
database is unreachable, stops the worker with status 1 and its reason in
one line, and its message stays on the queue. A broken worker is replaced
rather than left to fail every message it receives.

### Health

With `--heartbeat-file`, the worker touches a file before every receive and
after every extension. `azathoth worker health --heartbeat-file <PATH>`
exits with 0 when the file is younger than `--max-age-seconds`, 90 by
default, and 1 when it is not. It is a container health check with no server,
no port and no network.

### Inputs

The worker accepts no references, and never `file://`: a message from a
queue must never read the worker's own disk (ADR 0096). Every reference is
rejected:

```text
Input file:///etc/hostname uses the 'file' scheme, which is not accepted here; no schemes are accepted.
```

`s3://` references from allow-listed buckets, and a content store in S3, are
the worker's to accept next (ADR 0108).

### Output and tracing

Each settled message is one line of JSON on stdout:

```json
{"message_id": "059f36b4-87a3-44ab-83d2-661975830a7d", "idempotency_key": "order-4711-review", "status": "succeeded", "invocation_id": "5b0c2a52-0000-4000-8000-000000000001", "settled": "deleted"}
```

With tracing on, each job is traced as `job run` traces it, and its job span
carries `azathoth.worker.message_id` (ADR 0100).

### Verified across processes

The tests run real worker processes over a queue in a directory, which
stands in for SQS with its visibility timeouts and receipts. A worker stopped
with SIGTERM hands its job to the next, a killed worker's message comes back
and resumes once its lease lapses, and workers sharing a queue each take a
message once, with every mapped item running exactly once throughout. The
SQS queues themselves are tested call by call against botocore's `Stubber`.

### Not decided here

- `s3://` references and the S3 content store (ADR 0108).
- The deployment: the queues, their dead-letter queue, IAM, ECS and RDS
  (ADR 0109).

## Consequences

### Positive

- Programs run Azathoth by sending a message, and a fleet of workers shares
  the work through one database.
- A worker stopped by a deploy, or lost with its machine, costs no work that
  finished: the next worker resumes its run.
- Duplicate deliveries replay, and undecodable messages never come back.
- A health check needs nothing but the image.

### Negative

- A worker runs one job at a time, so a deployment of many short jobs needs
  many tasks.
- A result larger than SQS's message limit cannot be sent, and stops the
  worker. Results are recorded in the database whatever their size.
- The stand-in queue the tests share is not SQS, and nothing tests the two
  together before a real deployment does.
- The drain's signal handling is tested only where POSIX delivers signals.

## Alternatives Considered

### Several jobs per worker, with a connection pool

Deferred. It saves tasks, at the cost of a pool, of jobs that share a process
and its failures, and of a drain that waits on many runs at once. Scaling by
tasks needs none of it.

### An HTTP health endpoint

Rejected. A server and a port in every worker, for what a file's age says.

### Count receipts in the worker

Rejected. SQS's redrive policy already counts them, and moves a message aside
after as many as an operator chooses.

### Finish the running job on SIGTERM

Rejected. A job may run longer than any stop timeout, and would be killed
anyway. Cancelling it at once, with its lease released and its message handed
back, lets another worker resume it straight away.

### Exit with 143 after a drain

Rejected. A clean stop is the normal end of a worker's life, and 143 would
read as a failure in every task's history.

### Delete a message whose job is incomplete

Rejected. The run would have nothing left to bring it back to a worker once
its lease lapsed.

### moto's SQS server for the tests

Rejected for now. It could not be installed where these tests were written,
and the tests should run where they are written. The directory queue proves
the worker across processes; the `Stubber` proves its SQS calls.
