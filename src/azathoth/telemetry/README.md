# Telemetry

`azathoth.telemetry` traces what Azathoth runs with OpenTelemetry
(ADR 0100). A traced command exports one trace per request: the job, the
invocation it starts, the run that invocation executes, and every step of
that run, including every child workflow a step starts.

Tracing is opt-in twice over. It needs the `otel` extra:

```bash
python -m pip install "azathoth-ai[otel]"
```

and it is on only when the environment says so:

```bash
export AZATHOTH_OTEL=1
```

`AZATHOTH_OTEL` accepts `1`, `true`, `yes` or `on`, in any case. Without it,
Azathoth traces nothing and imports nothing of OpenTelemetry, whether or not
the extra is installed.

```python
from azathoth.telemetry import (
    NO_TELEMETRY,
    Telemetry,
    TelemetrySpan,
    active_telemetry,
    configure_from_environment,
    traced,
    use_telemetry,
)
```

## Configuration

Everything but `AZATHOTH_OTEL` is OpenTelemetry's standard configuration:

| Variable | Use |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where spans are sent, such as `http://localhost:4318` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Headers sent with them, such as a backend's API key |
| `OTEL_SERVICE_NAME` | The service spans are reported under; `azathoth` by default |
| `OTEL_RESOURCE_ATTRIBUTES` | Further resource attributes, such as `deployment.environment=prod` |
| `OTEL_TRACES_EXPORTER` | `otlp` (the default), `console` or `none` |

Spans are exported over OTLP with HTTP and protobuf. gRPC is not supported,
so the extra does not install `grpcio`. The console exporter writes spans to
stderr, so a command whose stdout is a contract, such as `job run`, still
prints only its own output there. The service version is always Azathoth's.

Spans are exported in batches, and flushed before a command exits, so a
short command loses none. A backend that cannot be reached never changes a
command's exit status, or what it prints on stdout.

A traced command that cannot trace runs nothing. With `AZATHOTH_OTEL` set
but the extra missing, it exits with status 1 after printing:

```text
AZATHOTH_OTEL is set, but OpenTelemetry is not installed; install azathoth-ai[otel].
```

An exporter Azathoth does not support is refused the same way:

```text
OTEL_TRACES_EXPORTER=zipkin is not supported; supported exporters: otlp, console, none.
```

## What Is Traced

`workflow run`, `workflow invoke` and `job run` are traced. Benchmark runs
and optimization are not traced in 1.1.

```text
azathoth.job          job run
└─ azathoth.invocation   workflow invoke, and the invocation a job starts
   └─ azathoth.run          every workflow run
      └─ azathoth.step         every step: executed, failed or skipped
```

`workflow run` starts at `azathoth.run`, and `workflow invoke` at
`azathoth.invocation`. A replayed or rejected job is one `azathoth.job` span,
because nothing is invoked.

A step span starts when its step starts and ends when it finishes, so the
concurrent steps of a layer overlap in time as they did in execution. A
skipped step, which never starts, is a span of no duration, so how often a
workflow escalated (ADR 0098) can be counted in any tracing backend.

Each failed attempt is an `azathoth.attempt.failed` event on its step's
span, carrying the attempt's number and exception type. A step that
succeeded on a retry keeps the events of the attempts that failed.

A failed span has status `ERROR` and an `error.type`:

| Span | `error.type` |
| --- | --- |
| `azathoth.job` | The job's error code, such as `idempotency_conflict` |
| `azathoth.invocation` | The invocation's error code, such as `workflow_execution_failed` |
| `azathoth.run` | The exception type of the step failure that halted it, or `WorkflowRunFailed` |
| `azathoth.step` | The exception type of its final attempt |

## Attributes

Spans carry identifiers, statuses and measurements, and nothing else:

| Attribute | Span | Meaning |
| --- | --- | --- |
| `azathoth.job.kind` | job | The job's kind, `invoke` |
| `azathoth.job.version` | job | The job's version, `1` |
| `azathoth.job.status` | job | `succeeded`, `failed`, `rejected` or `incomplete` |
| `azathoth.job.replayed` | job | Whether a recorded invocation was reported instead of a new one |
| `azathoth.invocation.id` | job, invocation | The invocation, for `azathoth invocation show` |
| `azathoth.invocation.outcome` | invocation | `succeeded`, or the error code |
| `azathoth.error.code` | job, invocation | The error code of one that did not succeed |
| `error.type` | any | Why a failed span failed |
| `azathoth.workflow.id` | invocation, run | The workflow |
| `azathoth.workflow.revision` | run | The workflow's revision, when the run records one |
| `azathoth.run.id` | run | The run, for `azathoth run show` |
| `azathoth.run.status` | run | `succeeded` or `failed` |
| `azathoth.run.steps.executed` | run | How many steps executed |
| `azathoth.run.steps.failed` | run | How many steps failed |
| `azathoth.run.steps.skipped` | run | How many steps were skipped |
| `azathoth.step.id` | step | The step |
| `azathoth.step.status` | step | `executed`, `failed` or `skipped` |
| `azathoth.step.attempts` | step | How many attempts it made |
| `azathoth.step.confidence` | step | The confidence it reported, when it declares one |
| `azathoth.strategy.name` | step | The strategy it ran |
| `azathoth.cost.usd` | step | Its estimated cost, when known |
| `azathoth.attempt.number` | attempt event | The failed attempt's number |
| `gen_ai.provider.name` | step | The model's provider |
| `gen_ai.request.model` | step | The model |
| `gen_ai.usage.input_tokens` | step | Prompt tokens |
| `gen_ai.usage.output_tokens` | step | Completion tokens |

The `gen_ai.*` attributes follow OpenTelemetry's generative AI conventions,
which are still marked experimental upstream. They, and the cost, appear
only as far as a step's execution reports them, so a tool step has none.

## No Content

A span never carries content: no workflow input, prompt, reply, output, step
value, tool input or output, tool stderr, and no error message, which can
quote any of those. A job span does not carry its idempotency key either,
which callers may build from their own identifiers. Content capture is not
offered in 1.1.

What happened is recorded in Azathoth's database, as it always was. A span
names the run, step and invocation it describes, so an operator follows a
trace into `azathoth run show` and `azathoth invocation show`.

## Child Workflows

While a step's span is current, a process tool it runs receives that step's
W3C trace context in its environment, as `TRACEPARENT` and, when there is
one, `TRACESTATE`. Both are managed by the engine: never inherited from
Azathoth's own environment, and never grantable (see the tools README's
[Process Environment](../tools/README.md#process-environment)).

A traced command whose environment holds `TRACEPARENT` parents its first span
under it. So a child `azathoth` that a tool starts continues its parent's
trace, under the step that started it:

```text
azathoth.invocation        parent
└─ azathoth.run
   └─ azathoth.step           run_workflow
      └─ azathoth.invocation     child
         └─ azathoth.run
            └─ azathoth.step
```

To export at all, the child needs the tracing configuration. The standard
composition tools grant `AZATHOTH_OTEL` and `OTEL_*` beside their other
grants. A tool of your own that runs `azathoth` grants them too.

## The Telemetry Protocol

The engine reaches OpenTelemetry only through `Telemetry`, so nothing else
in Azathoth imports it:

```python
class Telemetry(Protocol):
    @property
    def enabled(self) -> bool: ...

    def start_span(
        self, name, attributes=None, *, parent=None, start_time=None
    ) -> TelemetrySpan: ...
    def activate(self, span) -> object: ...
    def deactivate(self, token) -> None: ...
    def trace_context(self, span=None) -> dict[str, str]: ...
    def shutdown(self) -> None: ...
```

A `TelemetrySpan` takes attributes, events and an error type, and is ended
once. `NO_TELEMETRY` is the default: it is not enabled, its spans do
nothing, and its trace context is empty.

`configure_from_environment()` returns the telemetry the environment asks
for: `NO_TELEMETRY`, or one that exports through the SDK. The SDK adapter
lives in `azathoth.telemetry.sdk`, which is imported only then.

`active_telemetry()` is the telemetry this process traces with, and
`use_telemetry(telemetry)` replaces it, returning the previous one. The
traced commands make theirs active while they run, which is how a process
tool learns its step's trace context.

`traced(telemetry, name, attributes)` runs a block inside one current span.
An exception escaping the block marks the span failed with the exception's
type, never its message, and is raised again.

## Tracing Runs, Invocations and Jobs

The builders that know Azathoth's own records live beside the package's
public API, because they depend on the workflow and job models:

```python
from azathoth.telemetry.runs import TracingWorkflowRunner, traced_run, tracing_runner
from azathoth.telemetry.invocations import traced_invocation, traced_job, traced_job_invoker
```

- `tracing_runner(telemetry, observer=...)` returns a `TracingWorkflowRunner`
  when tracing is on, and a plain `WorkflowRunner` otherwise. A tracing
  runner traces every run it executes, and its steps, through a run observer
  combined with its own (see the workflows README's
  [Observing Progress](../workflows/README.md#observing-progress)).
  Concurrent runs on one runner never share a trace.
- `traced_run(telemetry, workflow_id=...)` opens one run span, and yields
  the observer that traces its steps and `record(run)`, which describes the
  span with the finished run.
- `traced_invocation(telemetry, workflow_id=...)` and `traced_job(telemetry)`
  open an invocation or job span; each yields `record(result)`.
- `traced_job_invoker(telemetry, invoke)` wraps a job invoker so each
  invocation it makes is traced under the job.

The attribute builders, in `azathoth.telemetry.attributes`, return
identifiers, statuses and measurements only. Every key they use is in
`ATTRIBUTE_KEYS`, and every span name in `SPAN_NAMES`.

## Not Decided Here

- Metrics. A collector's span metrics can derive cost, token and latency
  metrics from these spans' attributes.
- Tracing benchmark runs and optimization.
- Capturing content, for those who choose to.
- Logs.
