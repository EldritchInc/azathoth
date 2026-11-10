# ADR 0121: Service API, Second Round

- Status: Accepted
- Date: 2026-11-10

## Context

The service API of ADR 0120 covers what the command line and azathoth-mcp
did when it was made. The local editor, built on it alone, has found what
else it needs and cannot do without reaching past it: a run given a
document rather than JSON, a check of a workflow document that saves
nothing, the models a step could run on, the runs already made, and a try
of one step of a workflow not yet saved.

Each is assembled from what Azathoth already has. This record adds them to
the provisional API, one section each, without changing what a run, an
import or a model selection means.

## Decision

### A file as a run's input

`RunFile(content, media_type)` stands beside `RunInput(payload)`, and
`runs.run` and `runs.invoke` take either as their input. A file is accepted
as the command line's `--input-file` accepts one (ADR 0096, ADR 0112): JSON
and `text/*` content is decoded into the value the workflow receives, a
leading byte order mark dropped; a PDF, PNG, JPEG or WebP is checked against
its media type's signature, kept in the content store by its digest, and
given to the workflow as a content handle, with a `workflow.input.resolved`
event recording that it was inline, its size and its digest.

A file is checked before anything else, so a refused one starts no run,
records no invocation, and keeps nothing. Its refusal is an
`InvalidArgumentError` carrying the message ADR 0112 gives, such as:

```text
Content is not application/pdf: no PDF header in its first 1024 bytes.
```

A file larger than `MAX_INPUT_FILE_BYTES`, the 10 MB `--input-file` allows,
is refused:

```text
The input file is larger than the limit of 10485760 bytes.
```

A file has no name: nothing a run records would hold one, and a `file://`
URI would name a place the instance never read. An invocation's file is
part of its request, so the same file under the same key replays.

A separate type, rather than a field of `RunInput`, keeps a JSON null, which
is input, apart from a file, which is never mistaken for one.

### Checking a document

`workflows.check(document)` returns a `WorkflowCheck`: `valid` when
`workflows.import_document` would accept the document, and otherwise every
`DocumentProblem` it has. It saves nothing and asks no provider.

A problem has its `message`, its `location`, the keys and indexes leading to
the value at fault, and the `step_id` of the step it is in when that step's
id is valid. A rule of the whole workflow, such as that a step depends only
on steps in it, has an empty location: it is checked once every part is
valid on its own, so a document with both kinds shows the first kind first.

Pydantic tries each choice of a union, so a step whose specification is
wrong is wrong as a prompt, as a context prompt and as a tool at once. Each
union is reported as the choice it most nearly matched: the one lacking the
fewest values the document does not have, then with the fewest problems,
judged from the innermost union out. A prompt step missing its model
selection is told that, and not that it lacks a tool requirement:

```python
DocumentProblem(
    message="Field required",
    location=("steps", 0, "specification", "model_selection"),
    step_id=UUID("22222222-2222-2222-2222-222222222222"),
)
```

The choice's label is not part of the location, which names only what the
document holds. A collection too short once its refused items are left out
is not reported beside them.

A document without a result is not valid, with the message
`workflows.import_document` gives, at `("result",)`.

### Whether a document could run here

`runs.readiness(document)` returns a `WorkflowReadiness`: one
`StepReadiness` for each step, in the document's order, and `ready` when
every step is. It asks the providers what they serve, as a run does, and
resolves each step through the same code a run uses to make its candidate,
`generate_step_strategies`, which candidate generation now calls step by
step. The document need not have been imported, and nothing is saved.

A prompt step's `models` are those it could run on, in the order a run
tries them; a run uses the first. A tool step names the `tool_id`,
`tool_version` and `tool_implementation_id` it would run. A step that could
not run has a `problem`:

| Why | Problem |
| --- | --- |
| No model is in the portfolio | `The portfolio authorizes no model.` |
| None the portfolio holds meets its needs | `No model in the portfolio meets what this step needs.` |
| Its one model is not served | `Model '<identifier>' is not currently available.` |
| Its one model is served, but not runnable | `Model '<identifier>' is served, but cannot be run here.` |
| Its tool cannot be resolved | The message a run that could not start gives. |

It is under `runs`, not `workflows`, because it asks the providers, and
every call under `workflows` reads durable state alone.

### The models a step's needs match

`models.matching(requirements)` returns the portfolio's models that meet a
step's model requirements, as `ModelSummary` values, in the order a run
tries them. The requirements are what a step's `model_selection.requirements`
holds, and one left out is its default, so a step reads and writes text
unless it says otherwise. A model matches by `ModelQuery.matches`, the rule
a run applies. A requirement Azathoth does not know, or one that is not
valid, is refused with `InvalidArgumentError`, rather than ignored.

It names the models that meet the requirements, not that a provider here
can run them; `runs.readiness` says that.

### The runs already made

`runs.list(workflow_id, limit=None)` returns a workflow's kept runs as
`RunSummary` values, newest first, as `azathoth workflow runs` lists them: a
workflow since removed from configuration keeps its runs, and one neither
configured nor run is not found. `runs.get(run_id)` returns one as a
`RunDetail`, as `azathoth run show` shows it.

A run is judged by the revision that ran, so a run made before its
workflow's result was renamed still has its result. A run recorded before
revisions is judged by the latest; a run of a workflow no longer
configured has no declared result to judge it by, so it failed only if it
halted. `succeeded` and `error` mean what they mean for `runs.run`.

A run names the production `invocation_id` it executed, when it executed
one. Whether a run came from a benchmark or an experiment is not reported:
those records name their runs, and the API reads neither yet.

A `RunDetail` adds the run's input, kept apart from absence by `has_input`
as its result is by `has_result`; how often it was resumed; and every step
as a `RunStepDetail`, which extends the `RunStep` an invocation's run
already shows:

| Field | Holds |
| --- | --- |
| `layer` | The dependency layer it ran in. |
| `started_at`, `completed_at` | When its first attempt started and its last finished; None for a step that never ran. |
| `strategy` | The strategy an executed step ran. |
| `metrics` | Its provider, model, tokens, latency and estimated cost, as far as they were measured. |
| `output` | What an executed step's strategy returned. |
| `values` | The values it added to the run's context, by name, as `ContextChanged` reported them. |
| `failures` | Each attempt that failed, with its number, exception type and message. |

A run that journaled but never finished is not kept, so `runs.get`
raises `NotFoundError` with what `run show` says of it:

```text
Run <run-id> has not finished; resume it with azathoth run resume <run-id>.
```

### Trying one step

`runs.try_step(document, step_id, *, inputs=None, input=None, on_event=None,
cancel=None)` runs one step of a workflow document alone and returns a
`StepTrial`: the step as a `RunStepDetail`, as `runs.get` shows a run's, and
the warnings a run's result carries. The document need not have been
imported.

The step runs as the only step of a workflow of its own, made executable
as a run's candidate is, with what it depends on and its conditions taken
away:

- Each value `inputs` names takes the place of that input's source, as a
  constant would. A `RunFile` among them is checked and kept as a run's
  file is, and the step receives what a run would: a content handle for a
  document or an image, the value for JSON or text.
- An input not given keeps its source. A constant keeps its value, and a
  field of the run's input reads `input`, given as `runs.run` takes it; a
  field it was not given fails the step as it would fail a run's.
- An input that takes a value another step produces has no step to produce
  it, so it is refused with `InvalidArgumentError` unless it is given. So is
  a name the step has no input for.
- Its conditions are not asked: a step is tried to see what it does, not
  whether it would run.
- It is retried as its retry policy says, and its failure is the step's
  status, never an error.

Its `StepStarted`, `StepFinished` and `ContextChanged` events reach
`on_event` as a run's do; there is no run to start or finish, so neither
`RunStarted` nor `RunFinished` is sent. A cancellation token stops it as it
stops a run.

Nothing of the trial is kept: no run, no journal, no trace. The step is made
executable before a file given is kept, so a step that cannot start keeps
nothing; a file a step that starts was given stays in the content store,
by its digest, as any run's does. A step whose tool starts other workflows
starts them as a run's step would.

## Consequences

- The editor can run a workflow on a document someone drops on it, through
  its own server, and the run's evidence is what `--input-file` would have
  recorded.
- A document larger than 10 MB is given by reference, an S3 URI or a file
  the instance can read, as the command line gives one; the API takes no
  reference yet.
- The editor asks Azathoth what is wrong with a document, which models a
  step could choose, and whether the workflow could run, instead of
  repeating Azathoth's rules in TypeScript, and so cannot drift from them.
- The editor shows a finished run, its own or another's, from what the
  instance kept, with the same values a run it watched reported as it ran.
- The editor tries a step as it is written, on a document someone drops on
  it, before the workflow is saved or its other steps are finished.
- Candidate generation and readiness resolve a step through one function,
  so readiness never says a step could run where a run would refuse it.
