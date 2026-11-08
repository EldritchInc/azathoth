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
```

The not-found messages are the ones the matching CLI commands print.
