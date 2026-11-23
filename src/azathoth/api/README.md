# Service API

`azathoth.api` is Azathoth's public service layer (ADR 0120): the one
surface the command line, azathoth-mcp and the local editor call. It is
stable from 1.4.0, under Azathoth's 1.x compatibility promise: within 1.x it
grows only by additions, and anything removed waits for 2.0, after a minor
release that warns of it.

```python
from azathoth import api

with api.open("azathoth.db") as instance:
    description = instance.describe()

print(description.model_dump_json())
```

`api.initialize(database)` does what `azathoth init` does: it creates an
SQLite file, or creates or upgrades a PostgreSQL schema, and installs the
standard tool library, returning an `Initialization` that says which, and
which tools it installed. Running it again is always safe.

`api.open(database)` opens the instance one database holds, named as
`AZATHOTH_DATABASE` names it: an SQLite file's path, or a `postgresql://`
URL. Opening never creates or changes a database; `azathoth init` does.
Calls run synchronously on the caller's thread.

## Values

Every value the API returns is an `ApiModel`: frozen, closed to unknown
fields, and its own JSON, so `model_dump(mode="json")` can be sent as it is.
None of them is one of Azathoth's internal models.

`describe()` returns an `InstanceDescription`: the database as messages name
it (a PostgreSQL URL without its password), whether it is SQLite or
PostgreSQL, the Azathoth version, the schema version it uses, and the API's
stability, `provisional` or `stable`.

## Browsing

`instance.workflows`, `instance.tools` and `instance.benchmarks` read
durable state only, so no provider is reached and no credential is needed.

```python
from uuid import UUID

from azathoth import api

workflow_id = UUID("11111111-1111-1111-1111-111111111111")

with api.open("azathoth.db") as instance:
    summaries = instance.workflows.list()
    latest = instance.workflows.get(workflow_id)
    second = instance.workflows.get(workflow_id, revision=2)
    history = instance.workflows.history(workflow_id, limit=5)
```

| Call | Returns |
| --- | --- |
| `workflows.list()` | Every workflow at its latest revision, in first-import order. |
| `workflows.get(id, revision=None)` | One revision with its importable document, the latest by default. |
| `workflows.history(id, limit=None)` | Its revisions, newest first. |
| `workflows.export(id, revision=None)` | A `DocumentExport` of one revision, as `workflow export` prints it (ADR 0133). |
| `workflows.compare_revisions(id, before, after)` | A `RevisionComparison` of two revisions, as `workflow diff` prints it. |
| `tools.list()` | Every exact tool version at its latest revision. |
| `tools.versions(id)` | Each version of one tool at its latest revision, as `tool versions` lists them. |
| `tools.get(id, version, revision=None)` | One revision of one exact version, with its document. |
| `tools.history(id, version=None, limit=None)` | Its revisions newest first, of one version when it is named. |
| `tools.export(id, version, revision=None)` | A `DocumentExport` of one revision of one exact version. |
| `tools.compare_revisions(id, version, before, after)` | A `RevisionComparison` of two revisions of one exact version. |
| `tools.from_mcp(tool, url=None, command=(), authorization=None, grants=(), timeout_seconds=None)` | A `DocumentExport` of the tool an MCP server serves, pinned as it serves it now, as `tool from-mcp` prints it; nothing is imported. |
| `tools.install_standard()` | Each `StandardTool` of the standard library, installed as `tool install-standard` installs it; installing again changes nothing. |
| `benchmarks.list()` | Every benchmark dataset at its latest revision. |
| `benchmarks.get(id, revision=None)` | One revision with its document, the latest by default. |
| `benchmarks.history(id, limit=None)` | Its revisions, newest first. |
| `benchmarks.export(id, revision=None)` | A `DocumentExport` of one revision, with its `sensitivity`. |
| `benchmarks.compare_revisions(id, before, after, include_restricted=True)` | A `RevisionComparison` of two revisions; without `include_restricted`, a restricted case's values are withheld. |
| `benchmarks.cases(id, revision=None)` | Each `BenchmarkCaseSummary` of a revision, in order: its comparison, label, description, and where it came from, `run`, `file` or `json` (ADR 0130). |
| `benchmarks.case(id, case_id, revision=None)` | One `BenchmarkCaseDetail`, adding its input, expected value, citations, input provenance and metadata. |

`import_document(document)` on each of the three appends the next revision,
as the matching `import` command does, and returns it as `get` would. The
document is its JSON text, or its JSON values. A document that is not one,
a workflow that declares no result, a tool implementation in a runtime
Azathoth cannot run, or a tool artifact that belongs to another tool or
version is refused with `InvalidDocumentError`, and nothing is saved.

`workflows.check(document)` says whether importing a workflow document would
accept it, saving nothing. Its `problems` are every reason it would not,
each with its `message`, its `location` in the document, and the `step_id`
of the step it is in. A step is checked as the kind of step it most nearly
is, so a prompt step missing its model selection is not also told it lacks
a tool; a rule of the whole workflow is checked once every part is valid on
its own (ADR 0121).

Each value carries its `revision`: the number, the content digest, when it
was imported (`None` for revisions from before 1.1), and `identical_to`, the
earliest earlier revision with the same content when the import reverted to
one. A `get` also carries `latest_number` and the `document`, exactly what
the matching `import` command accepts. A benchmark also carries its
`sensitivity`, the most sensitive of its cases' labels (ADR 0123).

A `DocumentExport`'s `text` is exactly what the matching `export` command
prints, so importing the latest revision's export again appends nothing,
and its `file_name` suggests a file for it, such as
`word-count-1.0.0.r3.tool.json`; one made from an MCP server has no
revision yet, as `search-1.0.0.tool.json`. A benchmark's export carries its
label, so a caller can say it holds restricted data.

A `RevisionComparison` names both revisions, says whether they are
`identical`, by content digest, and lists each `RevisionChange` in document
order: its `kind`, `added`, `removed` or `changed`, its RFC 6901 JSON
`pointer`, and its `before` and `after` values. Objects are compared key by
key and lists item by item, so a case inserted first reads as each case
changing; nothing is guessed. Without `include_restricted`, which is the
`read_restricted` action, a restricted case's input, provenance, expected
value and citations are `None` and the change is `withheld`.

`tools.from_mcp` names the server by its `url` or by the `command` that
starts it, never both (`InvalidArgumentError`); a tool the server does not
serve is a `NotFoundError`, and a server that cannot be reached or listed,
or needs an authorization variable that is not set, is an
`McpUnavailableError`. Import the document with `import_document` once it
has been read.

Each value's `command` is the `azathoth` command that shows the same thing:
`workflow show` and `benchmark show`, with `--revision` for a revision named
by number, and `tool show --version` for a tool version, or
`tool export --version --revision` for one of its revisions, since
`tool show` cannot select a revision.

## Models and the Portfolio

An instance asks no model provider anything unless it is opened with
`ProviderSettings`. `ProviderSettings.from_environment()` reads
`OPENROUTER_API_KEY` and the Bedrock variables as the command line does;
nothing is reached, and boto3 is not imported, until a call needs a
provider's models.

```python
from azathoth import api

with api.open("azathoth.db", providers=api.ProviderSettings.from_environment()) as instance:
    models = instance.models.list()
    entry = instance.portfolio.add("openrouter/openai/gpt-4o-mini")
    removal = instance.portfolio.remove("openrouter/openai/gpt-4o-mini")
```

| Call | Does | Asks providers |
| --- | --- | --- |
| `models.list()` | Every model the providers serve now, provider by provider. | Yes |
| `models.get(identifier)` | One of them. | Yes |
| `models.usage(identifier)` | A `ModelUsage`: each workflow that configures the model, where its production uses it, and the runs that called it, as `model usage` prints it (ADR 0133). | No |
| `tools.usage(id)` | A `ToolUsage` of one tool identity, the same of a tool, with the names its versions are required by. | No |
| `models.matching(requirements, sensitivity=None, scope="portfolio")` | The portfolio's models that meet a step's requirements, in the order a run tries them; with `sensitivity`, only those that may receive input so labelled; with `scope="catalog"`, every served model that meets them, each marked `authorized` or not. | Yes |
| `portfolio.list()` | Every authorized model, in the order authorized. | No |
| `portfolio.add(identifier, data_policy=...)` | Authorizes a model a provider serves now. | Yes |
| `portfolio.set_data_policy(identifier, data_policy)` | Declares what its provider does with data, as `azathoth model policy` does. | No |
| `portfolio.remove(identifier, force=False)` | Removes a model, as `azathoth model deauthorize` does. | No |

Listing models records what each provider reports, as `azathoth model list`
does. A model's `authorized` says whether it is in the portfolio. Whatever a
provider does not publish, such as a context window or a price, is `None`.

A `PortfolioEntry` holds its `data_policy`, a `DataPolicy` of two
`PolicyAnswer`s, `retains_data` and `trains_on_data`, each `yes`, `no` or
`unknown` (ADR 0123). Both are unknown until declared, by `add` or by
`set_data_policy`, which replaces the policy and raises `NotFoundError` for a
model not authorized. `receives_restricted` says whether the model may be
sent restricted input: only when both answers are `no`.
`policy_declared_by` and `policy_declared_at` say who last declared the
policy, as the author the instance records, and when; both are None for a
policy never declared.

```python
instance.portfolio.set_data_policy(
    "openrouter/openai/gpt-4o-mini",
    api.DataPolicy(retains_data=api.PolicyAnswer.NO, trains_on_data=api.PolicyAnswer.NO),
)
```

`portfolio.remove` keeps a model that active production uses, raising
`ModelInUseError`, whose `dependents` names each workflow and step; with
`force=True` the model is removed and its `dependents` are returned. A
semantic judge is always kept until it leaves the judge rotation.

A usage is the `read_catalog` and `read_runs` actions. A model nothing uses
has no workflows, and is not an error; a tool nothing defines and no run
executed is a `NotFoundError`.

## Goals

`instance.goals` keeps the reusable goals strategies are measured against
(ADR 0133). A goal is not revised.

| Call | Returns |
| --- | --- |
| `goals.list()` | Each `GoalSummary`, in import order. |
| `goals.get(goal_id)` | One `GoalDetail`, adding its success criteria, constraints and document. |
| `goals.import_document(document)` | A `GoalImport`, as `goal import` does. |

Importing is the `import_goal` action. A document that is not a goal is an
`InvalidDocumentError`, refused before the database is touched; one
identical to the goal kept under its ID keeps nothing, and its `GoalImport`
is not `created`; another goal with a kept ID is a `ConflictError`, and the
kept one is never replaced.

## Judges

`instance.judges` keeps the rotation of models that judge semantic
benchmark cases, in the order they are tried (ADR 0129).

| Call | Returns |
| --- | --- |
| `judges.list()` | Every `JudgeSummary`, in rotation order: the model's identifier, provider and model, its `position` from 1, and whether the portfolio still `authorized` it. |
| `judges.add(identifier)` | The `JudgeSummary` appended, as `azathoth judge add` does. |
| `judges.remove(identifier)` | The `JudgeSummary` removed, as it was in the rotation. |

Judges see benchmark data, so a judge must be a model the providers serve
now (`NotFoundError` otherwise) and the portfolio authorizes
(`ModelNotAuthorizedError`); one already in the rotation is a
`ConflictError`. Listing and removing reach no provider.

## Benchmarks

`instance.benchmarks` also creates a benchmark, changes its cases, and
runs workflows against it (ADR 0130). Every change saves the benchmark's
next revision, so every execution still names the revision it ran.

| Call | Returns |
| --- | --- |
| `benchmarks.create(name, description, version="1.0.0")` | A `BenchmarkImport` of revision 1 of a new benchmark, with no cases. |
| `benchmarks.add_case(id, run_id= \| input= \| file=, file_uri=None, comparison, expected=KEEP, description=None, citations=None, sensitivity=None)` | A `BenchmarkCaseChange`: the case appended, and the revision saved, as `azathoth benchmark add-case` does. |
| `benchmarks.update_case(id, case_id, comparison=None, expected=KEEP, description=None, citations=KEEP, sensitivity=None)` | A `BenchmarkCaseChange` with only what is given changed; its ID, input and source stay. |
| `benchmarks.remove_case(id, case_id)` | A `BenchmarkCaseChange`: the case as it was, and the revision saved without it. |
| `benchmarks.executions(id, limit=None)` | Each `BenchmarkExecutionSummary`, newest first: `run` or `compare`, the revision it ran, its workflows best first, how many cases each passed, and its label. |
| `benchmarks.execution(execution_id)` | One `BenchmarkExecutionDetail`, adding each workflow's strategies, pass counts by comparison, judge totals and scorecard, and each case with its evaluation's score and reason. |
| `benchmarks.run(id, workflow_id, on_event=None, cancel=None)` | The `BenchmarkExecutionDetail` saved, as `azathoth benchmark run` does. |
| `benchmarks.compare(id, workflow_ids, target_latency_seconds, target_cost_usd, on_event=None, cancel=None)` | The `BenchmarkExecutionDetail` saved, ranked, as `azathoth benchmark compare` does. |

A case is made from exactly one of a recorded run, JSON given as a
`RunInput`, or a `RunFile`, with the `file_uri` it was read from when one is
known. A run's case expects the value given, or else the corrected output of
the run's latest bad judgment; any other case needs an expected value.
`expected=KEEP` gives none, since JSON null is a value; `citations=None`
clears what a case's run must cite in an edit, and `KEEP` leaves it. A case
is labelled as given, or as its run was, and its label may rise but never
fall. A case another case already is raises `ConflictError`.

`run` and `compare` check everything before any case runs, as the command
line does. `on_event` receives a `CaseStarted` and a `CaseFinished` for each
case of each workflow, on the caller's thread; a callback that raises is not
called again. `cancel` is checked between cases: a cancelled benchmark
raises `RunCancelledError`, keeps the runs of the cases it finished, and
records no execution.

## Runs

`instance.runs.run(workflow_id, input=None, sensitivity=None, on_event=None,
cancel=None)`
runs a workflow's latest revision as configured, as `azathoth workflow run`
does, and keeps the finished run whether it succeeded or failed. It returns
when the run has finished.

```python
from uuid import UUID

from azathoth import api

workflow_id = UUID("11111111-1111-1111-1111-111111111111")
token = api.CancellationToken()

with api.open("azathoth.db", providers=api.ProviderSettings.from_environment()) as instance:
    result = instance.runs.run(
        workflow_id,
        input=api.RunInput(payload="that is not dead which can eternal lie"),
        on_event=print,
        cancel=token,
    )
```

`RunInput` wraps the payload, so a JSON null is input and `None` is no
input: a run given none starts with an empty context. A run or an invocation
may be given a file instead, `RunFile(content=..., media_type=...)`, checked
and kept as `--input-file` is: JSON and text are decoded into the value, and
a PDF, PNG, JPEG or WebP of at most `MAX_INPUT_FILE_BYTES` is kept in the
content store and given to the workflow as a content handle; a file that is
not its media type is refused before anything runs (ADR 0121).

`run`, `invoke` and `try_step` each take `sensitivity`, a `Sensitivity`
labelling the input `PUBLIC`, `INTERNAL` or `RESTRICTED` (ADR 0123); without
one it is internal. The label is recorded with the run and inherited by
every child run it starts. It labels input, so `run` given one without
`input` raises `InvalidArgumentError` with
`SENSITIVITY_WITHOUT_INPUT_MESSAGE`:

```text
A sensitivity labels a run's input; give input too.
```

For `invoke` the label is part of the request a key is recorded with, and
for `try_step` it labels whatever `inputs` and `input` the step is given.

The `RunResult` says whether it `succeeded`, holds the declared `result`
when `has_result`, and
otherwise its `error`: the step that halted the run and its final failure
(`workflow_execution_failed`), or that it did not produce its declared
result (`result_not_produced`).

`on_event` is called on the run's thread with each event, in the order the
run makes them:

| Event | `type` | Carries |
| --- | --- | --- |
| `RunStarted` | `run_started` | The workflow, and the run it starts or resumes; None for an invocation's, named through its invocation. |
| `StepStarted` | `step_started` | The step, its dependency layer, and its message. |
| `StepFinished` | `step_finished` | Its status, its final failure's message, its confidence. |
| `ContextChanged` | `context_changed` | The values the step declared, by name. |
| `RunFinished` | `run_finished` | The kept run's ID, and whether it succeeded. |
| `InvocationFinished` | `invocation_finished` | The invocation, if one was made, and its status. |

Steps of one layer run together, so their events interleave. A callback
must return quickly. One that raises is detached for the rest of the run,
and the result's `warnings` name what it raised; the run carries on. Every
event is its own JSON, and `parse_run_event` reads one back.

`instance.runs.readiness(document)` says whether each step of a workflow
document, imported or not, could run here now, resolving it as a run would:
a prompt step to the `models` it could run on, in the order a run tries
them, and a tool step to the tool and implementation it would run. A step
that could not run says why in its `problem`, such as a model no provider
serves now or a tool not imported. It asks the providers, and saves nothing
(ADR 0121). With `sensitivity=`, each step is resolved as for a run whose
input is so labelled: a context prompt step of a restricted run could run
only on models declared to neither retain nor train on data, and one with
none says so, as the run's refusal would (ADR 0123).

`instance.runs.invoke(workflow_id, input=..., sensitivity=None,
idempotency_key=None, caller_metadata=None, on_event=None, cancel=None)` invokes the workflow's
active production state, as `azathoth job run` does, and returns an
`InvocationOutcome`: `succeeded` or `failed` with the invocation,
`rejected` when no invocation was made (such as an `idempotency_conflict`),
or `incomplete` while another process still runs it. The same request under
the same key replays its outcome, marked `replayed`, or resumes an
invocation whose run was stopped. Without a key, one beginning `api-` is
made. A workflow not in production fails as `workflow_not_deployed`; that
is an outcome, not an error. Every invocation ends with an
`InvocationFinished` event, a replay included.

`cancel.cancel()`, from any thread, stops the run where it is, as Ctrl-C
does: a running tool process is killed, nothing is kept as a finished run,
and `RunCancelledError` is raised; a cancelled invocation resumes when the
same request is made under its key. A token cancelled beforehand starts
nothing.

`instance.runs.list(workflow_id, limit=None)` returns a workflow's kept
runs newest first, as `azathoth workflow runs` lists them, and
`instance.runs.get(run_id)` one of them, as `azathoth run show` shows it.
Each run is judged by the revision that ran, and names the production
invocation it executed, if it executed one. A `RunDetail` holds the run's
input and result, how often it was resumed, and each step: its status and
layer, when its first attempt started and its last finished, its strategy
and what it measured, its output, the values it added to the context by
name, and every attempt that failed. A run that has not finished is not
kept yet, so `get` raises `NotFoundError` saying how to resume it
(ADR 0121). Every `RunSummary` holds the run's `sensitivity`: the most
sensitive of its input's label and its parent run's, `INTERNAL` when
neither is labelled (ADR 0123).

`instance.runs.record_feedback(run_id, disposition, reason=None,
corrected_output=None)` records one immutable `"good"` or `"bad"` judgment of
a kept run, as `azathoth run feedback` does, and returns it as a
`RunFeedback`; `instance.runs.feedback(run_id)` returns every judgment of a
run, newest first. A bad judgment needs a reason, a blank reason is none,
and a corrected output, what the run should have produced, is accepted only
with bad; each refusal is an `InvalidArgumentError`, and nothing is saved.
Every `RunSummary` and `RunDetail` holds the run's latest judgment as
`feedback`, `None` when it was never judged (ADR 0129).

`instance.runs.annotations(run_id)` and
`instance.invocations.annotations(invocation_id)` return an `Annotations`:
the W3C Web Annotation `collection` of every citation a run's steps
verified, exactly as `azathoth run annotations` prints it, its `items`, and
the run they are of. A run still under way exports what its committed
steps checked; an invocation exports its run's, and one with no run yet is
not found. A record the content store no longer holds raises
`ContentUnavailableError` (ADR 0129).

`instance.runs.children(run_id)` returns the runs a run's steps started,
oldest first, as `azathoth run children` lists them: each a
`RunChildSummary` with the child run and its workflow, the invocation it
executed when it was invoked, the parent's step and attempt that started
it, and its `status`, `"succeeded"` or `"failed"` as `runs.get` judges it,
or `"unfinished"` while no finished run is kept for it, when it has no
`command` yet. It works for a parent that never finished, since a child is
indexed as it starts; a run neither kept nor journaled raises
`NotFoundError` (ADR 0129).

`instance.runs.interrupted(workflow_id, limit=None)` lists a workflow's
runs that started and never finished, newest first, as `azathoth run
interrupted` does: each an `InterruptedRun` with the revision it started
from, when it started and last recorded anything, how often it was
resumed, the invocation it executes if it executes one, and the `command`
that resumes it. `instance.runs.resume(run_id, on_event=None, cancel=None)`
continues an interrupted configured run from its journal under its own ID,
as `azathoth run resume` does, reporting events as `runs.run` does, and
returns its `RunResult`. A run that executes an invocation resumes as its
invocation, with `invocations.resume`. A run that finished, executes an
invocation, is still held by another process, or whose journal cannot be
resumed raises `RunNotResumableError`; one never journaled raises
`NotFoundError` (ADR 0129).

`instance.runs.try_step(document, step_id, inputs=None, input=None,
sensitivity=None, on_event=None, cancel=None)` tries one step of a workflow document alone,
imported or not, and keeps no run. Each value `inputs` names, JSON or a
`RunFile`, takes the place of that input's source; an input not given keeps
its source, a constant its value and a field of the run's input the field of
`input`, while one another step produces must be given. The step's
conditions are not asked, it is retried as its policy says, its events
reach `on_event` as a run's do, and the `StepTrial` holds the step as
`runs.get` would show it (ADR 0121).

## Production

`instance.production` reads and changes what a workflow's production runs
(ADR 0128). Reading needs no provider; promoting asks the providers which
models they serve now, as a run does.

| Call | Returns |
| --- | --- |
| `production.get(workflow_id)` | The `ProductionState`: the workflow revision in production, the production revision that made it active (`None` when it was set without one), each prompt step's pinned model and approved substitutes, its input and output schemas, and the command that shows it; `None` when the workflow is not in production. |
| `production.revisions(workflow_id, limit=None)` | Its `ProductionRevisionSummary` items, newest first, with `active` marking the one production runs, each with its `author` and what it `restores`. |
| `production.promote(workflow_id, experiment_id=None)` | The `ProductionRevisionSummary` saved, as `azathoth workflow promote` does; with `experiment_id`, the experiment's winner, rebuilt from the latest revision (ADR 0092). |
| `production.roll_back(workflow_id, to=None)` | The `ProductionRevisionSummary` saved, as `azathoth workflow rollback` does: an earlier revision's state, the one before the active revision by default, restored as a new revision. |

A promotion or a rollback records who made it, told as an import's author
is. A workflow that is neither configured nor has production history raises
`NotFoundError`. A rollback is refused, and nothing changes, when there is
nothing earlier to restore (`NothingToRollBackToError`) or when a step of
the state it would restore has neither its fixed model nor any approved
substitute in the portfolio (`ModelNotAuthorizedError`).

## Experiments and Optimization

`instance.optimization` optimizes a workflow against a benchmark, and
`instance.experiments` reads, compares and checks what it recorded (ADR
0131). Reading and comparing need no provider; optimizing and `promotable`
ask the providers which models they serve now, as a run does.

| Call | Returns |
| --- | --- |
| `optimization.optimize(workflow_id, benchmark_id, target_latency_seconds, target_cost_usd, generations=1, on_event=None, cancel=None)` | An `OptimizationSummary`, as `azathoth workflow optimize` measures it: each generation's experiment, winner and proposals, the final evaluation or why it did not run, the winning experiment and the judge totals. |
| `experiments.list(workflow_id, limit=None)` | Each `ExperimentSummary`, newest first, as `azathoth workflow experiments` lists them: the benchmark and the revision it ran, its label, how many candidates and cases, and the winner's score. |
| `experiments.get(experiment_id)` | One `ExperimentDetail`, as `azathoth experiment show` prints it: every candidate ranked, with its scorecard, its cases, and the model each step ran on while its first case's run is kept. |
| `experiments.compare(experiment_id)` | An `ExperimentComparison`, as `azathoth experiment compare` prints it: the winner beside its baseline, what each run cost and took, the `savings` per run, the 30-day `projection`, and the promote `command`. |
| `experiments.promotable(experiment_id)` | A `Promotability`: whether `production.promote(workflow_id, experiment_id=...)` would rebuild the winner now, and its `code` and `reason` when it would refuse. Nothing is saved. |

`optimize` checks everything before any candidate runs: a benchmark with
no cases, a comparison no evaluator supports, a target not above zero or
fewer than one generation is an `InvalidArgumentError`, and a workflow
that declares no result a `WorkflowResultMissingError`. `on_event` receives
a `GenerationStarted`, a `CandidateFinished` for each candidate and a
`GenerationFinished` for each generation, the final evaluation told as one
more, on the caller's thread; a callback that raises is not called again.
`cancel` is checked between candidates: a cancelled session raises
`RunCancelledError` and keeps every experiment it finished.

A comparison's baseline is what production runs now, when the experiment
holds it, since promoting replaces it, and otherwise the configured
candidate, which every experiment of a session runs first; `baseline` is
`None`, with a `reason`, when the winner is its baseline or there is none.
Each side's cost and time are the means over its kept case runs, and a
cost is `None` when a model's pricing is unknown. The projection multiplies
the saving per run by production's invocations in the last 30 days; it is a
projection, never a measurement.

## Spend

`instance.spend` reports what an instance spent (ADR 0132). It reads the
database alone, and asks no provider.

| Call | Returns |
| --- | --- |
| `spend.report(since, until, period="day", group="workflow", time_zone="UTC", workflow_id=None)` | A `SpendReport`, as `azathoth spend` prints it: every period from `since` up to `until`, each with its `totals` and its `groups`, each group's totals over the whole range, the report's `totals`, and its `command`. |

Spend is a ledger of model calls, each counted once: each kept run's steps
that called a model, a production invocation's run as `production`, and
each judge call that replied as `judging`, on the workflow of the run it
judged. A step that started child runs is counted at its own cost, the
children's taken back out. `period` is `day`, `week`, an ISO week starting
Monday, or `month`, read in `time_zone`, an IANA name; `group` is
`workflow`, `model`, `provider` or `source`. Every time is told in the time
zone, with its offset, and every period of the range is listed, the first
and last cut to it.

A `SpendTotals` keeps `billed_usd` and `estimated_usd` apart, and counts the
`calls` and the `unpriced_calls`, whose cost is unknown. A time with no
offset, a `since` after its `until`, a period or grouping not listed, or a
time zone that is not one is an `InvalidArgumentError`; a `workflow_id`
neither configured nor spent on is a `NotFoundError`.

`spend_csv(report)` writes a report as CSV, its columns
`SPEND_CSV_COLUMNS`: a row for each group in each period, and one with no
group for a period nothing was spent in. It is RFC 4180, its times ISO 8601
with their offsets and its amounts unrounded.

## Invocations

`instance.invocations.get(invocation_id)` reads one invocation back, as
`azathoth invocation show` reports it: its workflow, when it was made, its
`status` (`succeeded`, `failed` or `incomplete`), its result or error, its
idempotency key, the input it was given, its `sensitivity`, its caller
metadata, and its run.
A finished run lists each step's status, attempts and confidence; a run
that has not finished names only its ID and how often it was resumed. Who
may read which invocation is the caller's to decide: azathoth-mcp, for
one, shows a caller only invocations it made.

| Call | Returns |
| --- | --- |
| `invocations.get(invocation_id)` | The `InvocationDetail`, as above. |
| `invocations.list(workflow_id, limit=None)` | Its `InvocationSummary` items, newest first, as `azathoth workflow invocations` lists them: when each was made, its `status`, its caller metadata, its `sensitivity`, and its run's ID once it has one (ADR 0128). |
| `invocations.resume(invocation_id, on_event=None, cancel=None)` | The `InvocationOutcome`, as `azathoth invocation resume` does: an incomplete invocation continues from the production state it started from, and its run from its journal, reporting events as `runs.invoke` does (ADR 0128). |

A workflow neither configured nor invoked is a `NotFoundError` to `list`.
`resume` refuses an invocation that has already completed, or that cannot
be resumed, as a `ConflictError`:

```text
Invocation <INVOCATION_ID> has already completed.
```

## Remotes

`instance.remote(url)` names a remote, served with `azathoth remote serve`,
to push to and pull from (ADR 0124). It is reached with `token=`, or the
token `AZATHOTH_REMOTE_TOKEN` holds, created on the remote with
`azathoth remote token create`:

```python
from uuid import UUID

from azathoth import api

workflow_id = UUID("11111111-1111-1111-1111-111111111111")

with api.open("azathoth.db") as instance:
    remote = instance.remote("https://azathoth.example.com")
    capabilities = remote.capabilities()
    pushed = remote.push(workflows=[workflow_id])
    pulled = remote.pull(workflows=[workflow_id])
```

| Call | Returns |
| --- | --- |
| `remote.capabilities()` | The remote's `Capabilities`: its protocol, versions, edition, plugins, and whether it accepts restricted data. |
| `remote.push(workflows=, tools=, benchmarks=)` | A `PushReport`: the revisions the remote received, numbered there, how many it held, and `warnings` of what would stop them from running there. |
| `remote.pull(workflows=, tools=, benchmarks=, include_restricted=False)` | A `PullReport`: the revisions saved here, the lineages forked, and the restricted benchmarks withheld. |
| `remote.status(workflows=, tools=, benchmarks=)` | A `RemoteStatus`: for each component named, or every one either side holds, its `Relation` (`in_sync`, `ahead`, `behind`, `diverged`, `local_only`, `remote_only`) and each side's latest revision; for each model, whether it is authorized here and at the remote. |

Tools are named as `(tool_id, version)`. A push sends each document's
latest revision, the revisions it was reached by, and what it needs there:
the tool versions its tool steps match, the child workflows its steps name,
and the content its benchmark cases hold, sending only what the remote
lacks. It moves the remote only forward; a lineage that diverged there is
refused, and is pulled first. A pull brings the same back, and forks a
lineage that diverged here on the revision it builds on. Restricted data is
pushed only to a remote that accepts it, and pulled only with
`include_restricted` (ADR 0123). What could not be gathered is named in
each report's `unresolved`. Production state and the portfolio never
travel.

A status reads the remote's portfolio whenever it reaches the remote, and
keeps it; a remote that cannot be reached is no error, but a status whose
remote side is unknown, each relation `None`, its models read from the last
portfolio kept, as of `portfolio_synced_at` (ADR 0125).

`instance.remotes` gives remotes names, so `instance.remote("origin")`
reaches the remote it names (ADR 0126). A name is 1 to 64 letters, digits,
`_` and `-`; it holds no `:`, `/` or `.`, so `instance.remote` reads
anything that does as a URL. Each name keeps the variable its token is read
from, `AZATHOTH_REMOTE_TOKEN` unless another is given, and never a token:

```python
with api.open("azathoth.db") as instance:
    instance.remotes.add("origin", "https://azathoth.example.com")
    instance.remotes.add(
        "staging",
        "https://staging.example.com",
        token_variable="AZATHOTH_STAGING_TOKEN",
    )
    pushed = instance.remote("staging").push(workflows=[workflow_id])
```

| Call | Returns |
| --- | --- |
| `remotes.list()` | Every `NamedRemote`, ordered by name: its `name`, `url`, `token_variable` and `added_at`. |
| `remotes.get(name)` | The `NamedRemote` of a name. |
| `remotes.add(name, url, token_variable="AZATHOTH_REMOTE_TOKEN")` | The `NamedRemote` it named, its URL without a trailing `/`. |
| `remotes.remove(name)` | The `NamedRemote` it forgot. The last portfolio read from its URL is forgotten too, unless another name is kept for it; nothing at the remote changes. |

A name already given is a `ConflictError`, and one never given a
`NotFoundError`:

```text
Remote <NAME> is already named, for <URL>; remove it first, or choose another name.
No remote is named '<NAME>'; name one with `azathoth remote add <NAME> <URL>`.
Remote name '<NAME>' is not one: use 1 to 64 letters, digits, '_' or '-'.
Token variable '<VARIABLE>' is not an environment variable's name: use letters, digits and '_', not beginning with a digit.
```

```text
No remote token was given; set <VARIABLE> to one created on the remote with `azathoth remote token create`.
Name a workflow, tool version or benchmark to send.
Remote URL '<URL>' is not an http or https URL.
```

A pulled workflow's steps may name requirements no model of this
portfolio meets, since the portfolio never travels.
`models.matching(step_requirements, scope="catalog")` names every model
the configured providers serve that meets them, each marked `authorized`
or not, so an operator can authorize one here; `MatchScope` names the two
scopes. A model outside the portfolio has no declared data policy, so it
never matches restricted input.

## Connecting to a Remote

`api.connect(url)` connects to the service API a remote serves (ADR 0137).
What it returns is an `Instance`, as `api.open` returns, whose every call
is sent to the remote and answered as the remote's policy allows; what it
changes there is recorded as the caller's. It is reached with `token=`, or
the token `AZATHOTH_REMOTE_TOKEN` holds, and `instance.remote(name).connect()`
connects to a remote this instance named, with the token its own variable
holds. Nothing is sent until a call is made:

```python
from azathoth import api


def names(instance: api.Instance) -> list[str]:
    return [workflow.name for workflow in instance.workflows.list()]


with api.open("azathoth.db") as local:
    here = names(local)

with api.connect("https://azathoth.example.com") as remote:
    there = names(remote)
```

`Instance` is a Protocol that `Azathoth` and `ConnectedInstance` both
satisfy: every collection of calls, `describe`, `closed` and `close`, but
`remote` and `remotes`, which no remote serves. A connected collection is
typed as the local one, and takes the same arguments, bound as Python
binds them; only those given are sent, so the rest take the call's
defaults at the remote. It is not the local class, and only its calls are
attributes.

A refusal raises the error the local call would have raised, of the
nearest kind this Azathoth knows, with the remote's message: a
`PermissionDeniedError` with the policy's reason, a `NotFoundError`, a
`ModelInUseError` with its `dependents`. Any call may also raise:

- `RemoteRefusedError`, for a refusal of no kind this Azathoth knows, with
  the `status` and the `refusal` code it was refused with, such as 401
  `unauthenticated`;
- `RemoteUnavailableError`, a `RemoteRefusedError` too, for such a refusal
  with 503, such as `audit_unavailable`, which may be tried again later;
- `RemoteUnreachableError`, for a remote not reached, or a server that
  answers as no remote serving the service API does.

The eight calls that take a callback for their events, such as `runs.run`,
are jobs a remote runs on its runners (ADR 0138): a connected instance
submits one, hands each event the remote streams to its `on_event`, asks
the remote to stop it once its `cancel` is cancelled, and returns its
result or raises its refusal, as the local call does. A callback that
raises is told no more, and the job goes on; a token cancelled before the
call sends nothing. A stream that drops is followed again from the last
event seen, up to 5 more times, and then given up while the job goes on.
A job of a remote that runs none is a `RemoteRefusedError`, 501 `job`, and
one a stopped server could not resume is a `RemoteRefusedError`, 409
`interrupted`, saying how to go on. Each other call is one request, and
once the instance is closed every call raises `InstanceClosedError`.

A connected instance's `jobs` reaches a remote's jobs apart from their calls. `submit`
queues one and returns its `JobAccepted` without waiting, `follow` waits
for one, handing on its events, and returns its result, `get` returns its
`JobView`, `list` the caller's own jobs, and `cancel` asks one to stop. A
local instance has no `jobs`:

```python
with api.connect("https://azathoth.example.com") as remote:
    accepted = remote.jobs.submit("benchmarks.run", benchmark_id, workflow_id)
    result = remote.jobs.follow(accepted.job_id)
```

```text
The remote at <URL> could not be reached: <REASON>
The remote at <URL> does not serve <CALL>; it may not serve the service API, which a remote does from Azathoth 1.6.
The remote at <URL> answered <CALL> with <STATUS> without saying why; it may not be an Azathoth remote.
The remote at <URL> answered <CALL> with something other than its result; it may serve another version of the service API.
The remote at <URL> dropped the events of job <JOB_ID> 6 times, so they are no longer followed; the job goes on there, and jobs.get finds it.
```

## Tracing and Content

`api.open(database, telemetry=..., content=...)` takes the telemetry that
traces runs and invocations, as `AZATHOTH_TRACING` does for the command
line, and the S3 location that keeps resolved content, as
`AZATHOTH_CONTENT_STORE` does. Without them, nothing is traced and content
is kept in the database.

## Actions

A remote asks its policy whether a caller may make each call, by the action
catalog's actions (ADRs 0127 and 0133), and tells its audit what the call
did. `azathoth.api.calls` lists each call once, as a `ServiceCall`, and each
call's docstring and this table say the same (ADR 0134):

- **Actions** are asked every time, for the resource the call names, such as
  a workflow by its `workflow_id`. A listing asks once, then for each
  resource it returns, and leaves out those refused.
- **Also** are asked only when what is written holds, such as
  `read_restricted` for a restricted case.
- **Audit** is what the call may tell the audit it did. Reading what is not
  restricted is not audited; reading restricted data always is.

A local instance asks nothing: its owner may do everything. The calls that
name this instance's own remotes are never served, since remotes never hold
each other's tokens.

A remote serves each other call at `POST /v1/calls/<NAME>`, its arguments
a JSON object by name and its answer the call's result as JSON, and
records what a caller changes as theirs (ADR 0136). The calls that take a
callback for their events, such as `runs.run`, are jobs a remote runs on
its runners, asking and telling as their calls do when they are submitted
(ADR 0138). The remote's README says how each call travels and is
refused.

| Call | Actions | Also | Audit |
| --- | --- | --- | --- |
| `describe` | `read_capabilities` |  |  |
| `remote` | never served |  |  |
| `workflows.list` | `read_catalog` |  |  |
| `workflows.get` | `read_catalog` |  |  |
| `workflows.history` | `read_catalog` |  |  |
| `workflows.check` | `read_catalog` |  |  |
| `workflows.export` | `read_catalog` |  |  |
| `workflows.compare_revisions` | `read_catalog` |  |  |
| `workflows.import_document` | `import_workflow` |  | `workflow_imported` |
| `tools.list` | `read_catalog` |  |  |
| `tools.versions` | `read_catalog` |  |  |
| `tools.get` | `read_catalog` |  |  |
| `tools.history` | `read_catalog` |  |  |
| `tools.export` | `read_catalog` |  |  |
| `tools.compare_revisions` | `read_catalog` |  |  |
| `tools.usage` | `read_catalog`, `read_runs` |  |  |
| `tools.import_document` | `import_tool` | `import_process_tool` for a process tool | `tool_imported`, `process_tool_imported` |
| `tools.from_mcp` | `tool_from_mcp` |  | `tool_made_from_mcp` |
| `tools.install_standard` | `install_standard_tools` |  | `standard_tools_installed` |
| `benchmarks.list` | `read_catalog` |  |  |
| `benchmarks.get` | `read_catalog` | `read_restricted` for a restricted benchmark | `restricted_read` |
| `benchmarks.history` | `read_catalog` |  |  |
| `benchmarks.export` | `read_catalog` | `read_restricted` for a restricted benchmark | `restricted_read` |
| `benchmarks.compare_revisions` | `read_catalog` | `read_restricted` for a restricted case | `restricted_read` |
| `benchmarks.cases` | `read_catalog` |  |  |
| `benchmarks.case` | `read_catalog` | `read_restricted` for a restricted case | `restricted_read` |
| `benchmarks.import_document` | `import_benchmark` |  | `benchmark_imported` |
| `benchmarks.create` | `edit_benchmark` |  | `benchmark_created` |
| `benchmarks.add_case` | `edit_benchmark` | `read_runs` when the case is made from a run; `read_restricted` when the case is made from a run of restricted input | `benchmark_case_added`, `restricted_read` |
| `benchmarks.update_case` | `edit_benchmark` |  | `benchmark_case_changed` |
| `benchmarks.remove_case` | `edit_benchmark` |  | `benchmark_case_removed` |
| `benchmarks.executions` | `read_runs` |  |  |
| `benchmarks.execution` | `read_runs` |  |  |
| `benchmarks.run` | `run_benchmark` |  | `benchmark_run` |
| `benchmarks.compare` | `run_benchmark` |  | `benchmark_run` |
| `goals.list` | `read_catalog` |  |  |
| `goals.get` | `read_catalog` |  |  |
| `goals.import_document` | `import_goal` |  | `goal_imported` |
| `models.list` | `read_portfolio` |  |  |
| `models.get` | `read_portfolio` |  |  |
| `models.matching` | `read_portfolio` |  |  |
| `models.usage` | `read_catalog`, `read_runs` |  |  |
| `portfolio.list` | `read_portfolio` |  |  |
| `portfolio.add` | `authorize_model` |  | `model_authorized` |
| `portfolio.set_data_policy` | `declare_policy` |  | `data_policy_declared` |
| `portfolio.remove` | `authorize_model` |  | `model_removed` |
| `judges.list` | `read_portfolio` |  |  |
| `judges.add` | `manage_judges` |  | `judge_added` |
| `judges.remove` | `manage_judges` |  | `judge_removed` |
| `runs.list` | `read_runs` |  |  |
| `runs.get` | `read_runs` | `read_restricted` for a run of restricted input | `restricted_read` |
| `runs.annotations` | `read_runs` |  |  |
| `runs.feedback` | `read_runs` |  |  |
| `runs.children` | `read_runs` |  |  |
| `runs.interrupted` | `read_runs` |  |  |
| `runs.readiness` | `read_catalog` |  |  |
| `runs.run` | `run_workflow` |  | `workflow_run` |
| `runs.try_step` | `run_workflow` |  | `step_tried` |
| `runs.invoke` | `invoke` |  | `workflow_invoked` |
| `runs.record_feedback` | `annotate_run` |  | `run_annotated` |
| `runs.resume` | `annotate_run` |  | `run_resumed` |
| `invocations.list` | `read_runs` |  |  |
| `invocations.get` | `read_runs` | `read_restricted` for a run of restricted input | `restricted_read` |
| `invocations.annotations` | `read_runs` |  |  |
| `invocations.resume` | `annotate_run` |  | `run_resumed` |
| `production.get` | `read_catalog` |  |  |
| `production.revisions` | `read_catalog` |  |  |
| `production.promote` | `promote` | `read_runs` when promoted from an experiment | `workflow_promoted` |
| `production.roll_back` | `promote` |  | `workflow_rolled_back` |
| `experiments.list` | `read_runs` |  |  |
| `experiments.get` | `read_runs` |  |  |
| `experiments.compare` | `read_runs` |  |  |
| `experiments.promotable` | `read_runs` |  |  |
| `optimization.optimize` | `optimize` |  | `workflow_optimized` |
| `spend.report` | `read_spend` |  |  |
| `remotes.list` | never served |  |  |
| `remotes.get` | never served |  |  |
| `remotes.add` | never served |  |  |
| `remotes.remove` | never served |  |  |

## Errors

Every error the API raises on purpose is an `ApiError` with a stable `code`:

| Error | Code | Raised when |
| --- | --- | --- |
| `InstanceNotFoundError` | `instance_not_found` | The SQLite file does not exist. |
| `InstanceUnavailableError` | `instance_unavailable` | PostgreSQL is named without the `postgres` extra. |
| `InstanceSchemaError` | `instance_schema` | The PostgreSQL database does not hold this Azathoth's schema. |
| `InstanceClosedError` | `instance_closed` | A call is made on a closed instance. |
| `NotFoundError` | `not_found` | No workflow, tool version, benchmark or goal has the ID named, no remote the name, or no MCP server serves the tool named. |
| `RevisionNotFoundError` | `revision_not_found` | It has no revision with the number named; a `NotFoundError` too. |
| `InvalidArgumentError` | `invalid_argument` | A history limit is below 1; a `ValueError` too. |
| `ConflictError` | `conflict` | A model is already authorized, or is a semantic judge, or another goal has the ID of one to import. |
| `ModelInUseError` | `model_in_use` | Active production uses the model; a `ConflictError` too. |
| `ProviderConfigurationError` | `provider_configuration` | Bedrock is on without boto3, without a region, or with unusable prices. |
| `ProviderUnavailableError` | `provider_unavailable` | A provider could not be asked what it serves. |
| `InvalidDocumentError` | `invalid_document` | A document to import is refused; an `InvalidArgumentError` too. |
| `InvalidAuthorError` | `invalid_author` | The author given, or `AZATHOTH_AUTHOR`, is not `Name <email>` or `Name`, or no author can be told; an `InvalidArgumentError` too. |
| `RunNotStartedError` | `run_not_started` | No executable candidate could be made, such as for a missing tool. |
| `WorkflowResultMissingError` | `workflow_result_missing` | A workflow to promote declares no result. |
| `ExperimentNotFoundError` | `experiment_not_found` | No experiment has the ID named; a `NotFoundError` too. |
| `CandidateUnavailableError` | `candidate_unavailable` | No candidate of a workflow to promote could be made with the models authorized now. |
| `CandidateRebuildError` | `candidate_rebuild` | An experiment's winner cannot be rebuilt from the latest revision; a `CandidateUnavailableError` too. |
| `NothingToRollBackToError` | `nothing_to_roll_back_to` | The workflow is not in production, has no earlier revision, or the one named is already active; a `ConflictError` too. |
| `ContentUnavailableError` | `content_unavailable` | Content a call reads, such as a run's record of citation checks, is not in the content store, or is not what it should be. |
| `ModelNotAuthorizedError` | `model_not_authorized` | A step of the state a rollback would restore has no model the portfolio authorizes, or a judge to add is not authorized; a `ConflictError` too. |
| `RunNotResumableError` | `run_not_resumable` | The run finished, executes an invocation, is still held by another process, or its journal cannot be resumed; a `ConflictError` too. |
| `RunCancelledError` | `run_cancelled` | The run's token was cancelled before it finished, a benchmark's between its cases, or an optimization's between its candidates. |
| `JudgeUnavailableError` | `judge_unavailable` | A benchmark's semantic cases have no judge that may judge them, or a judge failed; a `ConflictError` too. |
| `RemoteUnreachableError` | `remote_unreachable` | A remote was not reached, or answered as no remote does. |
| `RemoteProtocolError` | `remote_protocol` | A remote speaks another protocol; nothing was sent. |
| `RemoteRefusedError` | `remote_refused` | A remote refused a push or pull, or a call of a connected instance with no kind this Azathoth knows, or what it sent cannot be kept here. |
| `RemoteUnavailableError` | `remote_unavailable` | A remote refused a call with 503 and no kind this Azathoth knows, such as when its audit is down; it may answer later. A `RemoteRefusedError` too (ADR 0137). |
| `RemoteDivergedError` | `remote_diverged` | A pushed lineage diverged at the remote; a `ConflictError` too. |
| `McpUnavailableError` | `mcp_unavailable` | An MCP server to make a tool from could not be reached or listed, or needs an authorization variable that is not set. |
| `PermissionDeniedError` | `permission_denied` | A remote's policy refused the caller the call's action; its message is the policy's reason (ADR 0127). A local instance never raises it. |

```text
Database <PATH> does not exist; run azathoth init.
This Azathoth instance is closed.
Workflow <WORKFLOW_ID> is not configured.
Workflow <WORKFLOW_ID> has no revision <NUMBER>.
Tool <TOOL_ID>@<VERSION> is not configured.
Tool <TOOL_ID>@<VERSION> has no revision <NUMBER>.
Benchmark dataset <BENCHMARK_ID> is not configured.
Benchmark dataset <BENCHMARK_ID> has no revision <NUMBER>.
Tool <TOOL_ID> is not configured.
Goal <GOAL_ID> is not configured.
Goal <GOAL_ID> already exists.
MCP server <SERVER> serves no tool named '<TOOL>'.
A history limit must be at least 1.
Model '<IDENTIFIER>' is not currently available.
Model '<IDENTIFIER>' is already authorized.
Model '<IDENTIFIER>' is not authorized.
Model '<IDENTIFIER>' is a semantic judge and was not deauthorized; remove it from the rotation first with: azathoth judge remove <IDENTIFIER>
Model '<IDENTIFIER>' is used by active production and was not deauthorized.
Workflow document must declare a result.
The run was cancelled.
```

The not-found messages are the ones the matching CLI commands print.
