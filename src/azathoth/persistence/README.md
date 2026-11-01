# azathoth.persistence

`azathoth.persistence` is where Azathoth keeps its durable state: one SQLite
file, or one PostgreSQL database (ADR 0102, see
[Keep Durable State in PostgreSQL](../../../docs/adrs/0102-keep-durable-state-in-postgresql.md)).

Every repository is written once, against the `Database` protocol, and runs
on either database. SQLite stays the default: it needs no server and suits
one machine. PostgreSQL is for processes on several machines, or in several
containers, that share one store.

# Choosing a Database

`AZATHOTH_DATABASE` names the database. A value that starts with
`postgresql://` or `postgres://` names a PostgreSQL database; anything else,
including a Windows path with a drive letter, is the path of an SQLite file:

```bash
export AZATHOTH_DATABASE=/path/to/azathoth.db
export AZATHOTH_DATABASE=postgresql://azathoth:<PASSWORD>@db.example.com:5432/azathoth
```

`parse_database_location` turns the value into a `SQLiteLocation` or a
`PostgresLocation`.

The URL is a libpq connection URL, so its query parameters, such as
`sslmode=require` or `options=-csearch_path=azathoth`, reach the server
unchanged. Its credentials may sit in the URL, or in libpq's own places,
such as `PGPASSWORD` or a `.pgpass` file.

A URL may carry a password, so it is never shown as it is. `display()`, and
`redact_url` beneath it, remove the password and the `password`, `passfile`
and `sslpassword` parameters. Every message, including `azathoth init`'s,
names the database that way.

# The Driver

PostgreSQL needs psycopg 3, which the `postgres` extra installs:

```bash
python -m pip install "azathoth-ai[postgres]"
```

Importing `azathoth.persistence` imports nothing of psycopg; opening a
PostgreSQL database does. Without the extra, every command over a
PostgreSQL URL stops with:

```text
AZATHOTH_DATABASE names a PostgreSQL database, but psycopg is not installed; install azathoth-ai[postgres].
```

Azathoth supports PostgreSQL 15 and later, and CI tests 17.

# The Schema

A PostgreSQL database is created by `azathoth init`, and by nothing else.
`init` creates every table, records the schema's version, and installs the
standard tools. Several processes may run it at once: an advisory lock
serializes them, and the later ones find the schema already there. Running it
again is safe.

Every other command checks, once per process, that the database holds the
schema this Azathoth uses, and runs no DDL. A database that does not is
refused, and nothing is written:

```text
Database <URL> is not initialized; run azathoth init.
Database <URL> has schema version <FOUND>, but this Azathoth uses version <EXPECTED>; run azathoth init.
Database <URL> has schema version <FOUND>, newer than the version <EXPECTED> this Azathoth uses; upgrade Azathoth.
```

The version is `SCHEMA_VERSION`, kept in one row of the `azathoth_schema`
table.

An SQLite file needs no `init` to be used: each repository creates its
tables when it opens the file, and upgrades a file from before 1.1 in place,
as it always has. `init` still installs the standard tools into it.

## Tables

`SCHEMA_TABLES` holds every table, in the order `init` creates them:

| Table | Kept by |
| --- | --- |
| `workflow_specification_revisions` | `azathoth.workflows` |
| `workflow_production_states` | `azathoth.workflows` |
| `workflow_production_revisions` | `azathoth.workflows` |
| `workflow_runs` | `azathoth.workflows` |
| `workflow_run_evaluations` | `azathoth.workflows` |
| `workflow_run_feedback` | `azathoth.workflows` |
| `workflow_experiments` | `azathoth.workflows` |
| `workflow_experiment_observations` | `azathoth.workflows` |
| `workflow_benchmark_executions` | `azathoth.workflows` |
| `workflow_benchmark_execution_cases` | `azathoth.workflows` |
| `production_invocations` | `azathoth.workflows` |
| `production_invocation_results` | `azathoth.workflows` |
| `production_invocation_runs` | `azathoth.workflows` |
| `tool_definitions` | `azathoth.tools` |
| `tool_implementations` | `azathoth.tools` |
| `tool_test_cases` | `azathoth.tools` |
| `tool_document_revisions` | `azathoth.tools` |
| `benchmark_dataset_revisions` | `azathoth.evaluation` |
| `goals` | `azathoth.goals` |
| `judge_rotation_entries` | `azathoth.evaluation` |
| `models` | `azathoth.providers` |
| `model_portfolio_entries` | `azathoth.providers` |
| `provider_model_observations` | `azathoth.providers` |
| `content_blobs` | `azathoth.inputs` |

Documents and evidence stay JSON text, never `JSONB`, so what Azathoth reads
back is byte for byte what it wrote, and digests over it hold in either
database.

# Writing SQL Once

A statement is written once, with `?` parameters. On PostgreSQL, each `?`
outside a quoted string becomes `%s`, and each `%` is escaped.

A table is written once too, as a `Table` of `CREATE … IF NOT EXISTS`
statements. Where the two databases spell a column type differently, the
statement uses a token:

| Token | SQLite | PostgreSQL |
| --- | --- | --- |
| `{sequence}` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` |
| `{blob}` | `BLOB` | `BYTEA` |

The SQL itself is the subset the two share: no `GROUP BY` over columns that
are not grouped, no `INSERT OR IGNORE` (use `ON CONFLICT … DO NOTHING`), and
values read back through `require_text` and `require_integer`, which accept
what either driver returns.

A broken constraint raises one `IntegrityError` on either database, so a
repository maps a duplicate once. On PostgreSQL, a failed statement aborts
its transaction, so a repository that checks what a duplicate collided with
does so in a new one.

# Transactions and Locks

`Database.transaction()` runs a block as one transaction, committed when the
block returns and rolled back when it raises. `transaction(lock=table)`
also serializes the writers of one table, such as the revisions of one
specification, which are numbered in order:

| Database | A locked transaction |
| --- | --- |
| SQLite | `BEGIN IMMEDIATE` |
| PostgreSQL | `LOCK TABLE … IN EXCLUSIVE MODE`, which never blocks readers |

`Session.execute` returns the rows a statement changed; `fetchone` and
`fetchall` return rows of plain values.

# Connections

A PostgreSQL database keeps one connection for the life of the process,
opened when it is first used. A connection found closed or broken, such as
one the server dropped while it sat idle, is opened again before the next
transaction begins. Every repository over the same URL shares it.

A process with many connections to many databases, such as a queue worker,
needs a pool; ADR 0107 adds one.

# Opening the Repositories

`azathoth.persistence.repositories` composes every repository of one
database. It imports Azathoth's domain packages, which import
`azathoth.persistence` themselves, so it is imported by its full name:

```python
from azathoth.persistence.repositories import close_postgres_databases, open_repositories

repositories = open_repositories("postgresql://azathoth@db.example.com/azathoth")

try:
    workflows = repositories.workflows.specifications()
finally:
    close_postgres_databases()
```

`open_repositories` takes a location, a URL or a path. Nothing is opened
until a repository is first used, and each is opened once. An SQLite file is
served by the `SQLite…` repositories, which keep their in-place migrations; a
PostgreSQL database by the shared `Sql…` repositories over one
`PostgresDatabase`.

`close_postgres_databases` closes every PostgreSQL connection the process
opened. The CLI calls it when each command ends.

# Testing

`tests/persistence` runs every repository against SQLite, and against
PostgreSQL when `AZATHOTH_TEST_POSTGRES_URL` names a server. Each test gets
a schema of its own, dropped when it ends. See
[PostgreSQL Tests](../../../CONTRIBUTING.md#postgresql-tests).
