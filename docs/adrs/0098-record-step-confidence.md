# ADR 0098: Record Step Confidence

- Status: Accepted
- Date: 2026-10-31
- Decided in: #115

## Context

A step records what it produced, how long it took and what it cost, but not
how sure it was. Some steps know. A classifier asked for a category can say
how confident it is in the same JSON reply; a tool that matches patterns or
scores candidates knows its own margin.

That signal is what makes the most common cost pattern work: run a cheap
model first, and hand the work to a stronger one only when the cheap one is
unsure. Without it, a workflow either pays for the strong model on every
input or accepts the cheap model's mistakes.

The pieces for acting on a signal already exist. A step's declared outputs
are values. A condition compares a value with a constant, including with
`less_than` (ADR 0021). A value read by name is supplied by the first step
in declared order that produced it (ADR 0080). And every context event has
carried an optional `confidence` between 0 and 1 since ADR 0001, though no
step has ever set it.

What is missing is a way to say which value is a step's confidence, a rule
for what a valid confidence is, and a record of it beside the rest of the
step's evidence.

## Decision

### Declaring confidence

A step declares which of its own outputs is its confidence:

```json
{
  "outputs": [
    {"name": "category", "path": ["category"]},
    {"name": "confidence", "path": ["confidence"]}
  ],
  "confidence": "confidence"
}
```

`confidence` names one of the step's declared outputs; a name the step does
not declare makes the specification invalid. The output is extracted like any
other, by its `path`, so any step can declare confidence: a prompt step from
its JSON reply (ADR 0088), a tool step from its output.

A step without `confidence` serializes without it, so existing documents keep
their content digests (ADR 0077).

### Valid confidence

A confidence is a JSON number from 0 to 1, inclusive. An integer is accepted,
so `0` and `1` are valid. A boolean is not a number here, and percentages are
not accepted.

A confidence that is missing, out of range or not a number fails that attempt
with `WorkflowStepConfidenceError`:

```text
Workflow step <STEP_ID> confidence 'confidence' must be a number from 0 to 1; got 1.5.
```

It is retried under the step's retry policy, as an output that cannot be
resolved is (ADR 0081), because a model may report a valid confidence on a
later attempt. When attempts run out, the step fails under its own failure
policy. A missing confidence never passes silently: a step that cannot say how
sure it is must not be read as sure, nor as unsure.

### Recording confidence

A step that succeeds records its confidence:

- on its step run, as `confidence`, the record of authority;
- on each event its execution adds to the workflow's context, in the
  `confidence` field ADR 0001 defined.

A skipped step, a failed step, and a step that declares no confidence record
none. Runs recorded before this decision load unchanged, with no confidence.

`run show` names each step's confidence. A step that emits its values to the
JSON Lines stream (ADR 0083) carries its confidence on that `output` record:

```text
{"type": "output", "step_id": "...", "values": {...}, "confidence": 0.62}
```

`workflow show` names a step's confidence output.

### Escalating when unsure

Escalation is composed from steps, not built into one. An escalation step is
an ordinary step, usually a prompt step on a stronger model, conditioned on
the first step's confidence:

```json
"conditions": [
  {
    "source": {"producer_step_id": "<CLASSIFIER_STEP_ID>", "name": "confidence"},
    "operator": "less_than",
    "expected": 0.8
  }
]
```

The escalation step produces the same output names as the step it backs up,
and is declared before it in the workflow's step order. A consumer that
reads those values by name gets the escalation step's when it ran, and the
first step's when it was skipped (ADR 0080).

Because the escalation step is an ordinary step, everything that already
applies to steps applies to it: it is optimized on its own (ADR 0089),
resolved and substituted in production, counted in model usage and guarded
against deauthorization, and its cost and attempts are recorded. How often a
workflow escalated is visible as how often its escalation step ran.

The threshold is the condition's `expected` constant. Choosing it, and the
models on either side of it, is tuning, which belongs to the optimizer and
to the empirical evidence benchmarks produce, not to the runtime.

### Calibration

A confidence is only as good as whatever reports it. A model's self-reported
confidence is not calibrated, and Azathoth does not calibrate it. Whether
escalating on it improves a workflow is an empirical question, answered the
way every other one is: by running the workflow, with and without the
escalation, against a benchmark, and comparing quality, latency and cost.

### Callers

The job envelope and production emissions are unchanged. A workflow that
wants its callers to see a confidence emits it as a value, as it would any
other output.

### Not decided here

- Confidence derived from token log probabilities. Not every provider and
  model reports them, and they measure the reply's tokens, not the answer.
- A confidence or escalation-rate metric in scorecards, rankings or optimizer
  reports.
- A built-in escalation policy on prompt steps. If it comes, it is sugar over
  the same recorded confidence.

## Consequences

### Positive

- A workflow pays for a stronger model only on the inputs its cheap model is
  unsure about, using conditions and steps that already exist.
- Every step's confidence is recorded beside its output, cost and timing, so
  benchmarks and the optimizer have the evidence to judge an escalation.
- A step that fails to report a valid confidence is retried and then fails,
  instead of silently being treated as confident.
- Existing workflows, runs and digests are unchanged.

### Negative

- Escalation is two steps and a condition, and depends on declared step
  order, which a reader has to know about. The examples and the workflows
  README spell it out.
- Self-reported confidence is uncalibrated; a model can be confidently wrong.
  Only benchmarks show whether a threshold helps.
- The escalation step repeats the first step's work on the inputs it
  escalates, so those inputs cost both.

## Alternatives Considered

### A built-in escalation policy

Rejected for 1.1. An `escalation` field naming stronger models on a prompt
step would read well, but the runtime would have to rerun a step on another
model inside one step record, and candidate generation, production model
resolution, promotion's authorization checks and the model usage guards
would all need to know about models no step names. Composition gets all of
those for free.

### Confidence as its own path on the step

Rejected. Naming one of the step's outputs reuses output extraction and its
errors, and leaves the confidence available as a value for conditions with
no second mechanism.

### Record a missing or invalid confidence as none

Rejected. An escalation condition on a missing confidence would compare
nothing, and a step that never reports a usable confidence would never
escalate, or always would, with no failure to show why.

### A new rule for which producer wins

Rejected. Declared order already decides it reproducibly (ADR 0080). A rule
that preferred the escalation step would be a second resolution rule for one
pattern.
