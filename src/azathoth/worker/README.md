# Worker

`azathoth.worker` is the queue worker (ADR 0107). It takes job requests
(ADR 0097) from a queue, one message at a time, and settles each message by
its job's result.

```python
from azathoth.worker import (
    JobQueue,
    QueueMessage,
    ResultQueue,
    Worker,
    WorkerSettings,
)
```

## Queues

A `JobQueue` delivers each message at least once. A received message is
hidden from other receivers for its visibility timeout, and is delivered
again once that runs out, unless it was deleted:

- `receive(wait_seconds=..., visibility_timeout_seconds=...)` returns the
  next `QueueMessage`, or `None` when none arrived within the wait;
- `delete(message)` removes it for good;
- `change_visibility(message, timeout_seconds=...)` hides it for that long
  from now, and `0` makes it visible again at once.

A `QueueMessage` carries the queue's `message_id`, the `receipt_handle` of
this receipt, and its `body`, which is exactly one job request.

A `ResultQueue` is sent every final result:
`send(body, idempotency_key=...)`, where the body is the one line of JSON
`azathoth job run` prints for it.

Every method blocks, and the worker calls them from a thread.

## Settling a Message

`Worker(queue, handle)` runs each message's body with `handle`, which
answers every request with a job result. Its result settles the message:

| Result | Message |
| --- | --- |
| `succeeded`, `failed`, `rejected` | Sent to the result queue, when there is one, then deleted. |
| `incomplete` | Left, to come back when its visibility timeout runs out. |

A result is sent before its message is deleted, so a worker that dies in
between sends it again when the message comes back, as a replay.

A request that does not decode is `rejected`, so it is deleted rather than
received again and again. A message that keeps stopping workers, as one
that kills the process would, is the queue's to move aside, with a
dead-letter queue.

While a job runs, the worker extends its message's visibility, so the
message is not delivered again under a live run. An extension the queue
refuses is reported, and the job carries on: the run's lease keeps a second
worker from running it at the same time (ADR 0105).

Each settled message is one line of JSON on stdout:

```json
{"message_id": "059f36b4-87a3-44ab-83d2-661975830a7d", "idempotency_key": "order-4711-review", "status": "succeeded", "invocation_id": "5b0c2a52-0000-4000-8000-000000000001", "settled": "deleted"}
```

`settled` is `deleted`, `left` or `returned`. A message handed back, or left
because its job raised, has a `null` status and invocation.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `wait_seconds` | 20 | How long one receive waits for a message, at most 20. |
| `visibility_timeout_seconds` | 120 | How long a received message stays hidden, at most 43200. |
| `extend_every_seconds` | 30 | How often a running job's message is hidden again. |

Visibility must be extended more often than it runs out:

```text
A worker must extend a message's visibility more often than its visibility timeout of <SECONDS> seconds.
```

## Stopping

`await worker.run(stop)` receives and settles messages until the
`asyncio.Event` is set. A receive already waiting finishes first. Then the
job running is cancelled, which releases its run's lease as it unwinds, and
its message is made visible again at once, so another worker resumes the run
from its journal instead of waiting out the timeout. A message received as
the stop arrives is handed back without running.

## Failures

A handler never raises for a request's own problems; those are results. One
that raises means the worker cannot run jobs, as when its database is
unreachable. The message stays on the queue, the reason is written on
stderr, and `run` raises the error, so the worker is replaced instead of
failing every message it receives:

```text
Message <MESSAGE_ID> stays on the queue; running it failed: <REASON>
Could not extend the visibility of message <MESSAGE_ID>: <REASON>
```

A queue that fails also raises from `run`.

## Heartbeat

`heartbeat` is called before every receive and after every extension, so a
health check can tell a live worker from a stuck one.
