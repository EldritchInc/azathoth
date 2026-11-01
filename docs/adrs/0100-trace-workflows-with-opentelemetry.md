# ADR 0100: Trace Workflows With OpenTelemetry

- Status: Accepted
- Date: 2026-11-01
- Decided in: #117

## Context

Azathoth records every run as evidence in its own database: each step, each
attempt, the model it used, its tokens, cost, latency and confidence. That
is enough to inspect one run from a terminal. It is not where a platform
team looks when something is slow, expensive or failing in production. They
look at their tracing backend, beside every other service they run.

Azathoth 1.1 runs on AWS, behind a queue, invoked by programs through the job
envelope (ADR 0097), and composes workflows from child processes (ADR 0084).
A request crosses several processes, and an operator needs to follow it
across all of them in one place.

OpenTelemetry is the standard way to do that: vendor-neutral, configured by
standard environment variables, and exported to anything from a local
collector to CloudWatch, Honeycomb or Datadog.

Two things constrain how. Most Azathoth users do not trace, and should not
pay for it in dependencies or behavior. And the workflows Azathoth runs see
customer tickets, contracts and, at a healthcare company, patient data;
nothing a trace carries may expose that.

## Decision

### Opt-in

Tracing is an optional extra:

```bash
python -m pip install "azathoth-ai[otel]"
```

It installs `opentelemetry-api`, `opentelemetry-sdk` and
`opentelemetry-exporter-otlp-proto-http`. Azathoth's own dependencies are
unchanged; the engine reaches OpenTelemetry only through
`azathoth.telemetry`, whose default does nothing and imports nothing.

Tracing is on only when the environment says so:

```bash
export AZATHOTH_OTEL=1
```

Everything else is configured the standard way: `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME` (default `azathoth`),
`OTEL_RESOURCE_ATTRIBUTES`. Spans are exported over OTLP with HTTP and
protobuf; `OTEL_TRACES_EXPORTER=console` prints them instead, for debugging.
gRPC is not supported, so the extra does not install `grpcio`.

A command that traces with `AZATHOTH_OTEL` set but without the extra fails
before it runs anything, with exit status 1:

```text
AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel].
```

Spans are exported in batches and flushed before the command exits, so a
short command loses none.

### What is traced

In 1.1, `workflow run`, `workflow invoke` and `job run` are traced. Benchmark
runs and optimization, which run a workflow many times per command, are a
separate decision.

```text
azathoth.job          job run
└─ azathoth.invocation   workflow invoke, and the invocation a job starts
   └─ azathoth.run          every workflow run
      └─ azathoth.step         every step: executed, failed or skipped
```

A step span starts when its step starts and ends when it finishes, so spans
are live: a run that crashes has still exported its finished steps, and
concurrent steps of a layer overlap in time as they did in execution. A
skipped step is a span of no duration, so how often a workflow escalated
(ADR 0098) can be counted in any tracing backend.

Each failed attempt is an event on its step's span, carrying its attempt
number and exception type. Attempts are not spans of their own.

### Attributes

Spans carry identifiers, statuses and measurements:

| Span | Attributes |
| --- | --- |
| `azathoth.job` | `azathoth.job.kind`, `azathoth.job.version`, `azathoth.job.status`, `azathoth.job.replayed`, `azathoth.invocation.id`, `azathoth.error.code` |
| `azathoth.invocation` | `azathoth.invocation.id`, `azathoth.workflow.id`, `azathoth.invocation.outcome`, `azathoth.error.code` |
| `azathoth.run` | `azathoth.run.id`, `azathoth.workflow.id`, `azathoth.workflow.revision`, `azathoth.run.status`, executed, failed and skipped step counts |
| `azathoth.step` | `azathoth.step.id`, `azathoth.step.status`, `azathoth.step.attempts`, `azathoth.strategy.name`, `azathoth.step.confidence`, `azathoth.cost.usd`, and the model attributes below |

A prompt step's model is described with OpenTelemetry's generative AI
conventions, which are still marked experimental upstream:
`gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`
and `gen_ai.usage.output_tokens`. A failed span has status `ERROR` and an
`error.type` attribute naming the exception type.

### No content

A span never carries content: no workflow input, prompt, reply, output, step
value, tool input or output, tool stderr, and no error message, which can
quote any of those. A job span does not carry its idempotency key either,
which callers may build from their own identifiers.

What happened is recorded in Azathoth's database, as it always was. A span
names the run, step and invocation it describes, so an operator follows a
trace into `run show` and `invocation show`. Content capture is not offered
in 1.1.

### Child workflows

While a step span is active, a process tool's environment gains the W3C
trace context of that step, `TRACEPARENT` and, when there is one,
`TRACESTATE`. Like `AZATHOTH_TOOL_TIMEOUT_SECONDS`, they are managed by the
engine: never inherited from Azathoth's own environment, and never grantable
(this amends ADR 0099).

A traced command whose environment holds `TRACEPARENT` parents its first span
under it. So a child `azathoth` started by a tool continues its parent's
trace, under the step that started it.

To export at all, the child needs the tracing configuration. The standard
composition tools grant `OTEL_*` and `AZATHOTH_OTEL` beside their existing
grants, as implementations 1.0.2 and 1.1.2: the next revisions of the same
tool versions, for the reason ADR 0099 gives for its own grants.

### Not decided here

- Metrics. A collector's span metrics can derive cost, token and latency
  metrics from these spans' attributes.
- Tracing benchmark runs and optimization.
- Capturing content, for those who choose to.
- Logs.

## Consequences

### Positive

- An operator follows one request, across the job, its invocation, its run,
  each step and every child workflow, in the tracing backend they already use.
- Cost, tokens, latency, model, retries, confidence and escalation are
  visible per step, without querying Azathoth's database.
- Azathoth's dependencies and behavior are unchanged for anyone who does not
  trace.
- A trace exposes no workflow content, so tracing can be turned on for
  workflows that handle sensitive data.

### Negative

- The generative AI conventions are experimental and may rename attributes;
  following them may mean renaming attributes in a later release.
- A trace alone cannot say why a step failed; the message is in `run show`.
- The standard composition tools gain another revision, and a database that
  installed them before needs `install-standard` again.
- Benchmarks and optimization are not traced yet.

## Alternatives Considered

### Depend on `opentelemetry-api` always

Rejected. It is the usual pattern for a library, and the API does nothing
without an SDK, but Azathoth is an application with three dependencies, and
most of its users would install a fourth for nothing.

### Trace by default whenever the extra is installed

Rejected. The SDK's default exporter sends to a local collector, so
installing the extra without one would fill every command's output with
export errors.

### Build spans afterwards from the recorded run

Rejected. It would match the evidence exactly, but a crash would export
nothing, and a long run would export nothing until its end.

### Record content, redacted

Rejected for 1.1. Redaction cannot know what in a ticket or a contract is
sensitive, and a trace that is safe only most of the time is not safe.

### Attempts as child spans

Rejected. Most steps have one attempt, and an event per failed attempt says
everything a span would, at a fraction of the volume.
