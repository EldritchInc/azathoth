# ADR 0087: Bind Prompt Variables to Step Inputs by Name

- Status: Accepted
- Date: 2026-10-26
- Decided in: #104

## Context

A workflow step receives its inputs as `workflow.input.bound` context events,
one per input, each carrying the input's `name` and `value`.

A `PromptBinding` resolves a template variable from "the latest event of one
type, one field of its payload". Every bound input has the same event type, so
a prompt step could reach only the input bound last. A step with a plan, notes
and a chapter number could not render all three.

Values were also inserted with `str.format_map`, so a dict or list reached the
model as a Python representation (`{'a': 1}`, `True`) rather than as JSON.

Every checked-in prompt example had a single string input, which is why
neither problem surfaced earlier.

## Decision

A template variable may bind a step input by its name:

```json
{"variable_name": "plan", "input_name": "plan"}
```

`PromptInputBinding` takes the value of the latest `workflow.input.bound`
event whose `name` matches. The runner binds a step's own inputs last, so an
earlier step's input of the same name never wins.

`PromptTemplate.bindings` holds either form. Both binding models forbid
unknown keys, so a binding mixing the two forms is rejected rather than
silently matching one.

A step whose template binds an input it does not declare is rejected when the
specification is constructed:

```text
Workflow step <STEP_ID> prompt variable 'plan' binds input 'plan', which the step does not declare.
```

At render time, a missing input raises `PromptBindingInputNotFoundError`.

Every bound value now renders the same way, for both binding forms. Strings
are inserted unchanged. Every other value is compact JSON with non-ASCII
characters kept:

```text
{"title":"Café","chapters":2}    ["Ada","Grace"]    true    null    18
```

Templates are still formatted with `str.format_map`, so literal braces in a
prompt, such as an example JSON reply, must be doubled: `{{"verdict": "pass"}}`.

`PromptBinding` is unchanged, so existing documents keep their content
digests (ADR 0077). `WORKFLOW_INPUT_BOUND_EVENT_TYPE` names the event, and the
runner uses it instead of repeating the string.

## Consequences

### Positive

- A prompt step can render every input it declares.
- Structured values reach models as JSON.
- A binding to a missing input fails when the workflow is built.

### Negative

- Non-string values bound through event fields render differently than
  before. No checked-in example inserted one.
- Literal braces in templates still need doubling.

## Alternatives Considered

### A dedicated event type per input

Rejected. It would change the evidence every run records, and couple event
names to input names.

### Replace `format_map` with another template syntax

Rejected. It would break every existing template for one escaping rule.
