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

## Errors

Every error the API raises on purpose is an `ApiError` with a stable `code`:

| Error | Code | Raised when |
| --- | --- | --- |
| `InstanceNotFoundError` | `instance_not_found` | The SQLite file does not exist. |
| `InstanceUnavailableError` | `instance_unavailable` | PostgreSQL is named without the `postgres` extra. |
| `InstanceSchemaError` | `instance_schema` | The PostgreSQL database does not hold this Azathoth's schema. |
| `InstanceClosedError` | `instance_closed` | A call is made on a closed instance. |

```text
Database <PATH> does not exist; run azathoth init.
This Azathoth instance is closed.
```
