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
- Candidate generation and readiness resolve a step through one function,
  so readiness never says a step could run where a run would refuse it.
