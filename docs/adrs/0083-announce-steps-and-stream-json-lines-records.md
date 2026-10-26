# ADR 0083: Announce Steps and Stream JSON Lines Records

- Status: Accepted
- Date: 2026-10-25
- Decided in: #101

## Context

ADR 0056 rendered a configured run once, as a human-readable report, after it
finished. That serves an operator reading a terminal. It serves nothing else:
a program calling Azathoth, a parent workflow, or anyone watching a slow
workflow progress.

Workflow authors also had no way to say what a step is doing in words meant
for whoever is watching.

## Decision

A step may declare a `message`, announced when it starts, and may set
`emit_values` to also emit its declared values once it succeeds. A step without
a message is silent. Only a step with a message, and with declared outputs,
may emit values. Both fields are presentation only: they never change how a
step executes, is evaluated or is optimized.

`WorkflowRunner(observer=...)` reports progress live through
`WorkflowStepStarted` and `WorkflowStepFinished` events. Observation never
changes recorded evidence, and anything an observer raises is discarded.

`workflow run` and `workflow invoke` take `--output jsonl|text|result`. The
default is JSON Lines: one JSON object per line, flushed as written.

```text
{"type": "step", "step_id": "...", "message": "..."}
{"type": "output", "step_id": "...", "values": {...}}
{"type": "result", "run_id": "...", "value": ...}
{"type": "error", "run_id": "...", "code": "...", "message": "..."}
```

The stream ends with exactly one `result` or `error` record. A run without a
declared result omits `value`, so it cannot be mistaken for a result of
`null`. A `delta` record is reserved for streamed model output.

`text` keeps the human-readable report, and `result` prints only the result
value. Errors before execution starts are text on standard error in every
format.

Configured runs report a halting step's actual failure, because they are the
workflow author's tool. Production invocations report only the caller-visible
error code and message (ADR 0065).

## Consequences

### Positive

- Programs and parent workflows can consume runs without parsing reports.
- Long workflows show progress live.
- Authors control what watchers see, step by step.

### Negative

- The default output is for programs; people reading a terminal pass
  `--output text`.

## Alternatives Considered

### Keep the report as the default

Rejected. Programs are the primary consumer of a run's output, and a report is
not a stable interface.

### Emit every step's values automatically

Rejected. Intermediate values are often large, internal or sensitive; emission
is the author's choice.
