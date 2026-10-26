# ADR 0067: Deliver External Input Through One Canonical Event

- Status: Accepted
- Date: 2026-09-09
- Decided in: #87, #102

## Context

A workflow receives external input from several sources: benchmark cases
during optimization, production invocations from callers, and operators
running a configured workflow.

If each source placed its input in context differently, a prompt or tool bound
to "the input" would render one way while being optimized and another way in
production. Optimization would then be measuring something production never
runs.

## Decision

Every external input source emits the same context event:

```text
event type   workflow.input.received
payload      {"input": <value>}
```

`create_workflow_input_event` builds it, and `WORKFLOW_INPUT_EVENT_TYPE` names
it. Only the producer differs:

```text
azathoth.benchmark       benchmark cases
azathoth.production      production invocations
azathoth.configured      workflow run --input
```

Production invocations also record their own `production.invocation.received`
event, which invocation history reads. The canonical event is the one
workflows bind to.

Workflow steps bind to the input with a context reference:

```json
{"event_type": "workflow.input.received", "field_name": "input"}
```

A configured run without `--input` starts from an empty context, as before.
With `--input`, the value is parsed as JSON. A supplied `null` stays distinct
from no input at all.

## Consequences

### Positive

- A workflow renders identically whether it is benchmarked, invoked or run.
- New input sources need no workflow changes.
- The producer still records where an input came from.

### Negative

- Workflows must bind to the event explicitly; there is no implicit "input"
  variable.

## Alternatives Considered

### Let each input source define its own event

Rejected. Optimized and production behavior would diverge.

### Pass input to steps outside the context

Rejected. Context is Azathoth's single record of what a run observed
(ADR 0001).
