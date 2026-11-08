# Service API

`azathoth.api` is Azathoth's public service layer (ADR 0120): the one
surface the command line, azathoth-mcp and the local editor call. It is
provisional until 1.4.0, and may change between 1.4 pre-releases.

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
| `tools.list()` | Every exact tool version at its latest revision. |
| `tools.get(id, version, revision=None)` | One revision of one exact version, with its document. |
| `tools.history(id, version=None, limit=None)` | Its revisions newest first, of one version when it is named. |
| `benchmarks.list()` | Every benchmark dataset at its latest revision. |
| `benchmarks.get(id, revision=None)` | One revision with its document, the latest by default. |
| `benchmarks.history(id, limit=None)` | Its revisions, newest first. |

`import_document(document)` on each of the three appends the next revision,
as the matching `import` command does, and returns it as `get` would. The
document is its JSON text, or its JSON values. A document that is not one,
a workflow that declares no result, a tool implementation in a runtime
Azathoth cannot run, or a tool artifact that belongs to another tool or
version is refused with `InvalidDocumentError`, and nothing is saved.

Each value carries its `revision`: the number, the content digest, when it
was imported (`None` for revisions from before 1.1), and `identical_to`, the
earliest earlier revision with the same content when the import reverted to
one. A `get` also carries `latest_number` and the `document`, exactly what
the matching `import` command accepts.

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
| `portfolio.list()` | Every authorized model, in the order authorized. | No |
| `portfolio.add(identifier)` | Authorizes a model a provider serves now. | Yes |
| `portfolio.remove(identifier, force=False)` | Removes a model, as `azathoth model deauthorize` does. | No |

Listing models records what each provider reports, as `azathoth model list`
does. A model's `authorized` says whether it is in the portfolio. Whatever a
provider does not publish, such as a context window or a price, is `None`.

`portfolio.remove` keeps a model that active production uses, raising
`ModelInUseError`, whose `dependents` names each workflow and step; with
`force=True` the model is removed and its `dependents` are returned. A
semantic judge is always kept until it leaves the judge rotation.

## Runs

`instance.runs.run(workflow_id, input=None, on_event=None, cancel=None)`
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
input: a run given none starts with an empty context. The `RunResult` says
whether it `succeeded`, holds the declared `result` when `has_result`, and
otherwise its `error`: the step that halted the run and its final failure
(`workflow_execution_failed`), or that it did not produce its declared
result (`result_not_produced`).

`on_event` is called on the run's thread with each event, in the order the
run makes them:

| Event | `type` | Carries |
| --- | --- | --- |
| `RunStarted` | `run_started` | The workflow. |
| `StepStarted` | `step_started` | The step, its dependency layer, and its message. |
| `StepFinished` | `step_finished` | Its status, its final failure's message, its confidence. |
| `ContextChanged` | `context_changed` | The values the step declared, by name. |
| `RunFinished` | `run_finished` | The kept run's ID, and whether it succeeded. |
| `InvocationFinished` | `invocation_finished` | The invocation, if one was made, and its status. |

Steps of one layer run together, so their events interleave. A callback
must return quickly. One that raises is detached for the rest of the run,
and the result's `warnings` name what it raised; the run carries on. Every
event is its own JSON, and `parse_run_event` reads one back.

`instance.runs.invoke(workflow_id, input=..., idempotency_key=None,
caller_metadata=None, on_event=None, cancel=None)` invokes the workflow's
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

## Invocations

`instance.invocations.get(invocation_id)` reads one invocation back, as
`azathoth invocation show` reports it: its workflow, when it was made, its
`status` (`succeeded`, `failed` or `incomplete`), its result or error, its
idempotency key, the input it was given, its caller metadata, and its run.
A finished run lists each step's status, attempts and confidence; a run
that has not finished names only its ID and how often it was resumed. Who
may read which invocation is the caller's to decide: azathoth-mcp, for
one, shows a caller only invocations it made.

## Tracing and Content

`api.open(database, telemetry=..., content=...)` takes the telemetry that
traces runs and invocations, as `AZATHOTH_TRACING` does for the command
line, and the S3 location that keeps resolved content, as
`AZATHOTH_CONTENT_STORE` does. Without them, nothing is traced and content
is kept in the database.

## Errors

Every error the API raises on purpose is an `ApiError` with a stable `code`:

| Error | Code | Raised when |
| --- | --- | --- |
| `InstanceNotFoundError` | `instance_not_found` | The SQLite file does not exist. |
| `InstanceUnavailableError` | `instance_unavailable` | PostgreSQL is named without the `postgres` extra. |
| `InstanceSchemaError` | `instance_schema` | The PostgreSQL database does not hold this Azathoth's schema. |
| `InstanceClosedError` | `instance_closed` | A call is made on a closed instance. |
| `NotFoundError` | `not_found` | No workflow, tool version or benchmark has the ID named. |
| `RevisionNotFoundError` | `revision_not_found` | It has no revision with the number named; a `NotFoundError` too. |
| `InvalidArgumentError` | `invalid_argument` | A history limit is below 1; a `ValueError` too. |
| `ConflictError` | `conflict` | A model is already authorized, or is a semantic judge. |
| `ModelInUseError` | `model_in_use` | Active production uses the model; a `ConflictError` too. |
| `ProviderConfigurationError` | `provider_configuration` | Bedrock is on without boto3, without a region, or with unusable prices. |
| `ProviderUnavailableError` | `provider_unavailable` | A provider could not be asked what it serves. |
| `InvalidDocumentError` | `invalid_document` | A document to import is refused; an `InvalidArgumentError` too. |
| `RunNotStartedError` | `run_not_started` | No executable candidate could be made, such as for a missing tool. |
| `RunCancelledError` | `run_cancelled` | The run's token was cancelled before it finished. |

```text
Database <PATH> does not exist; run azathoth init.
This Azathoth instance is closed.
Workflow <WORKFLOW_ID> is not configured.
Workflow <WORKFLOW_ID> has no revision <NUMBER>.
Tool <TOOL_ID>@<VERSION> is not configured.
Tool <TOOL_ID>@<VERSION> has no revision <NUMBER>.
Benchmark dataset <BENCHMARK_ID> is not configured.
Benchmark dataset <BENCHMARK_ID> has no revision <NUMBER>.
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
