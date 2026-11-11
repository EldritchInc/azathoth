# ADR 0123: Sensitivity Labels

- Status: Accepted
- Date: 2026-11-10

## Context

Azathoth sends a run's data to models. Until 1.4 it could not tell a public
press release from a patient's chart, so an operator who handles regulated
data, records under HIPAA say, had no way to say which models that data may
reach, and nothing stopped a step, a judge or an optimizer from sending it
to a model whose provider keeps what it is sent, or trains on it.

1.4's remote will push benchmarks and runs to shared instances and pull them
back. Before anything travels, Azathoth needs to know what is sensitive, and
which destinations may receive it.

## Decision

### Three labels, on the input

Data is `public`, `internal` or `restricted`, ranked in that order, never by
name. The label belongs to a run's input, and to a benchmark case: content
in the content store carries none, since the same bytes may be restricted in
one run and public in another, and are kept once.

Data that names no label is internal. An unlabelled input, case, lineage or
record is stored without a label, so everything made before labels
serializes, and digests, as it did. A label is given where input is:

```bash
azathoth workflow run <WORKFLOW_ID> --input-file chart.pdf --sensitivity restricted
azathoth workflow invoke <WORKFLOW_ID> --input '{"claim":412}' --sensitivity restricted
```

and in an input source's `sensitivity`, a job's input, the service API's
`sensitivity=` on `runs.run`, `runs.invoke` and `runs.try_step`, a benchmark
case and `benchmark add-case --sensitivity`. A labelled run records its
label in a `workflow.input.sensitivity` event after its input's events. A
label given without input starts nothing:

```text
A sensitivity labels a run's input; give input too.
```

### A label is never lowered

A run's label is the most sensitive of its input's and its parent run's.
Lineage carries it, so a child workflow is never less sensitive than the run
that started it, whatever its own input was labelled, and a running step
reads it as `active_step_lineage().sensitivity`. A case made from a run
takes the run's label; one labelled lower is refused:

```text
Run <RUN_ID> is restricted; a case made from it cannot be internal.
```

A benchmark is as sensitive as its most sensitive case, and its executions
and experiments record the label of the revision they ran against.

### Restricted means declared private

A model may receive restricted input only when its portfolio entry declares
that its provider neither retains nor trains on the data it is sent. Each
answer is `yes`, `no` or `unknown`, and unknown counts as not allowed.
Azathoth assumes no provider's terms: the operator declares them, when
authorizing or after,

```bash
azathoth model authorize <MODEL_IDENTIFIER> --no-retention --no-training
azathoth model policy <MODEL_IDENTIFIER> --no-retention --no-training
```

and the service API's `portfolio.add(data_policy=)` and
`portfolio.set_data_policy`. An entry of unknown policy serializes without
one, so no entry's digest changes. Who declared a policy, and when, is
recorded beside the entry, never in it, so it is no part of the entry's
digest: schema version 4 adds `model_portfolio_policy_declarations`, which
`model policy` shows, and each declaration replaces the last.

Public and internal data may reach any model the run may use.

### Enforced where data is sent

Every path by which Azathoth sends a run's data to a model is guarded:

| Path | Guard |
| --- | --- |
| A context prompt step | Refuses, before anything is sent, a model that may not receive the running step's label |
| Choosing a step's model | Tries the models that may receive the run's label first; production prefers one among the primary and its approved substitutes |
| Semantic judges | Refuses a judge that may not receive the label of the semantic cases it judges |
| Optimization | Substitutes only private models into a restricted context prompt |
| Readiness and matching | `runs.readiness` and `models.matching` take a label |

The refusal names the step, the model and the declaration that forbids it,
and how to fix it:

```text
Step <STEP_ID> sent nothing. <MODEL> cannot receive restricted input: its portfolio entry does not say whether its provider retains data, and does not say whether it trains on data. If its provider neither retains nor trains on data, declare that with `azathoth model policy <MODEL> --no-retention --no-training`; otherwise choose a model that may receive restricted input.
```

It holds none of the input, so a production invocation's caller is told it
in place of the usual `Production workflow execution failed.`, and can tell
an operator what to declare. Production chooses its models from its
production state, never the portfolio; it reads the portfolio, as it is
when an invocation runs, only for each model's declared policy, so a model
declared private serves the next restricted invocation without promoting
again.

A fixed prompt holds only its own text, so it is not guarded. Tools are not
guarded in 1.4: a tool step receives a restricted run's data as any run's.

### MCP clients are destinations too

An MCP client is often itself a model, so azathoth-mcp returns restricted
data only through a tool the operator exposes for it:

```json
{"workflow_id": "<WORKFLOW_ID>", "name": "summarize_chart", "description": "Summarize a patient's chart.", "sensitivity": "restricted"}
```

That is the operator's declaration that the client, a HIPAA assistant
calling a HIPAA workflow say, may hold restricted data. Every call of the
tool is labelled restricted, so it is guarded as above, and a call that
cannot be served says why. `get_invocation` refuses a restricted invocation
through a tool not so exposed.

### Labels are shown wherever data is

The service API's run, invocation and benchmark views carry `sensitivity`.
`run show`, `invocation show`, `benchmark show`, `benchmark case-show`,
`benchmark execution-show` and `experiment show` name a label that is not
internal. Every command that prints a restricted run's, invocation's or
benchmark's data warns of it on standard error, after its output:

```text
Run <RUN_ID> is restricted; its output contains restricted data.
```

A run's span names its label as `azathoth.sensitivity`, an attribute, never
content, so a collector can route or drop restricted runs' traces. Nothing
is redacted in 1.4.

### Push and pull come with the remote

1.4's remote will refuse to push restricted data to a destination not
declared to receive it, with the same helpers: `most_sensitive`,
`require_no_lower` and `may_receive`.

### What labels guard

Labels guard Azathoth's own paths out: its prompts, judges, optimizer, MCP
results, output and traces. They keep an operator from sending restricted
data somewhere by mistake. They do not guard against a tool written to
carry data elsewhere: a tool runs with the run's data, and may do what its
author wrote. Nor do they stop someone who may run workflows from making
unrestricted data of restricted data, by calling a child workflow with a
part of it they judged unrestricted, from a tool; the child's lineage still
names its parent, so that is recorded.

Tool data policies, and an explicit, recorded declassification for the
team tier, come later in 1.4.x.

## Consequences

- An operator can run regulated data through Azathoth and say, model by
  model, where it may go; a restricted run that would reach anywhere else
  sends nothing and says why.
- Nothing changes for data that is not labelled: no digest, dump, output or
  model choice differs.
- A restricted run whose models are not declared private fails until an
  operator declares them. Declaring is the operator's word, not something
  Azathoth checks with the provider.
- A PostgreSQL database must be initialized again for schema version 4, as
  for any new schema version.
- Commands that print restricted data write a warning to standard error,
  which JSON Lines output otherwise keeps empty once execution starts.

## Alternatives Considered

### Labels on content

Labelling blobs in the content store would label the same bytes once for
every run that holds them, though one run's restricted chart is another's
public sample. A label says how one run treats its input, so it lives on the
input.

### Provider defaults

Shipping each provider's retention and training terms would have Azathoth
vouch for contracts it has not read, which change and differ by account. An
unknown answer that refuses restricted data is safe; a wrong default is
not.

### Lowering a label

Letting a case or child be labelled lower than its source would make every
label a suggestion. Declassification needs a recorded decision by someone
allowed to make it, which the team tier will add.

### Redacting restricted output

Redaction needs to know what in the output is sensitive, which a label on
the whole run cannot say. The warning tells the operator what they hold;
redaction can follow.

### Gating tools now

A tool's data policy needs a vocabulary for what a tool does with data, and
a way to declare it per tool version. That waits for 1.4.x, so 1.4 says
plainly that tools are not gated.
