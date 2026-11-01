# ADR 0102: Keep Durable State in PostgreSQL

- Status: Accepted
- Date: 2026-11-01
- Decided in: #119

## Context

Azathoth keeps everything durable in one SQLite file: workflows, tools,
benchmarks, goals and their revisions; models and the portfolio; runs,
experiments, promotions, invocations and their idempotency keys; and the
content of resolved inputs.

That is right for a laptop. It is not enough for Azathoth 1.1 on AWS. There,
many containers, from the image of ADR 0101, run at once: queue workers
taking jobs, operators promoting workflows, child workflows started by
tools. Each container has its own filesystem, so they can only share state
through a database server, and the one AWS runs for them is PostgreSQL, on
RDS or Aurora.

Three things make this easier than it sounds:

- Every repository already has a protocol and an in-memory implementation,
  so the engine never names SQLite. Only the CLI does, when it composes the
  repositories it uses.
- The SQL is mostly portable. A repository stores an indexed key and the
  record's canonical JSON. Upserts, `COALESCE(MAX(...))` and ordering by an
  increasing sequence mean the same in both databases.
- The standard composition tools already grant `AZATHOTH_DATABASE` (ADR 0099),
  so a child workflow uses whatever database its parent names.

Four things differ: how an increasing sequence is declared, how binary
content is stored, how a transaction takes the lock that numbers revisions
safely, and how the parameters of a statement are written.

## Decision

### Selecting PostgreSQL

`AZATHOTH_DATABASE` names either database. A `postgresql://` or
`postgres://` URL selects PostgreSQL; anything else is an SQLite path, as
today:

```bash
export AZATHOTH_DATABASE="postgresql://azathoth:<PASSWORD>@db.example.internal:5432/azathoth"
```

The URL carries the credentials, with the password URL-encoded. In AWS, the
whole URL is injected from Secrets Manager. libpq's own `PG*` variables are
not used: a child workflow would not see them without another revision of
the standard tools. Anything Azathoth prints about the database shows the
URL with its password hidden.

PostgreSQL 15 or newer is supported. CI tests 17.

### An optional extra

PostgreSQL support is an optional extra, like tracing:

```bash
python -m pip install "azathoth-ai[postgres]"
```

It installs psycopg 3, as `psycopg[binary]`, whose wheels carry libpq for
macOS, Windows and Linux on both architectures, so no system package is
needed. Azathoth's own dependencies are unchanged, and nothing of psycopg is
imported unless the database is PostgreSQL. A PostgreSQL URL without the
extra fails before the command does anything, with exit status 1:

```text
AZATHOTH_DATABASE names a PostgreSQL database, but psycopg is not installed; install azathoth-ai[postgres].
```

The container image (ADR 0101) includes the extra.

### One implementation, two dialects

A new package, `azathoth.persistence`, holds what the two databases share:

- the parsed database location;
- a small `Database` protocol, whose transactions execute statements, and can
  take an exclusive lock on one table;
- `SQLiteDatabase` and `PostgresDatabase`, which implement it.

Each repository is written once, against `Database`: one `Sql…` class per
repository, such as `SqlWorkflowRunRepository(database)`. Its statements are
written once, with `?` parameters, and its tables once, with a token for each
difference:

| Token | SQLite | PostgreSQL |
| --- | --- | --- |
| `{sequence}` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` |
| `{blob}` | `BLOB` | `BYTEA` |

A uniqueness violation surfaces as one error, whichever database raised it,
so a repository maps it, for example to `IdempotencyKeyInUseError`, once.

Every existing `SQLite…(path)` class stays, as a thin constructor that opens
an `SQLiteDatabase` at the path. Code and tests that build SQLite
repositories directly are unchanged.

### Payloads stay text

Records are stored as their canonical JSON in `TEXT` columns, in PostgreSQL
as in SQLite, never as `JSONB`. `JSONB` reorders keys and drops duplicates,
so a stored record would no longer read back exactly as written, and content
digests and revision identity (ADR 0077) depend on exact content.

### Schema

A PostgreSQL schema is created deliberately, never as a side effect:

- `azathoth init` creates the schema in one transaction, under an advisory
  lock, so several containers may run it at once. It records the schema's
  version in an `azathoth_schema` table, starting at 1, the shape the tables
  have today. Running it again is safe.
- Opening a PostgreSQL database checks that version, and never runs DDL. A
  database that is not initialized, or is older than this Azathoth, is
  refused before anything runs:

  ```text
  Database postgresql://azathoth@db.example.internal:5432/azathoth is not initialized; run azathoth init.
  ```

SQLite keeps creating its tables when a repository opens them, and keeps the
in-place migrations of databases from before 1.1. A later change to the
schema is a numbered migration for both databases, applied by `init`.

### Revisions under concurrency

Numbering a new revision reads the latest number and writes the next, so two
writers must never interleave. SQLite takes `BEGIN IMMEDIATE`, which locks
the whole file. PostgreSQL takes `LOCK TABLE … IN EXCLUSIVE MODE` on the
revision table inside the writing transaction, which serializes writers and
never blocks readers. The unique constraint on each artifact's revision
numbers remains the last guard in both.

A table's sequence orders its records as they were committed, closely
enough for "insertion order" to keep its meaning under concurrent writers,
as SQLite's file lock does.

### Connections

A `PostgresDatabase` opens one connection when it is first used, and keeps
it for the life of the process. Each repository call is a transaction of its
own. A connection the server dropped is opened again once. SQLite keeps a
connection per call.

Pooling belongs to long-lived processes, and is decided with the queue
worker (ADR 0107).

### Composition

`open_repositories(location)` returns every repository for one database,
typed by its protocol, and the CLI composes its repositories only through it.

### Verified on both

A contract suite runs every repository's behavior on both databases: SQLite
always, and PostgreSQL when `AZATHOTH_TEST_POSTGRES_URL` names a server, each
test in a schema of its own. `make postgres-test` runs it against a
throwaway `postgres:17` container. CI runs it, with a lifecycle through the
CLI from `init` to a child workflow, in a job with a PostgreSQL service. The
test matrix stays on SQLite.

### Not decided here

- Copying an SQLite database into PostgreSQL. Workflows, tools, benchmarks
  and goals move between databases as documents already.
- Connection pooling (ADR 0107).
- IAM authentication to RDS, and where the URL is kept (ADR 0109).

## Consequences

### Positive

- Any number of containers share one durable state, on RDS or Aurora.
- Each repository's behavior is written and tested once, for both databases.
- Nothing changes for SQLite: no migration, no new dependency, and every
  existing class and test keeps working.
- Child workflows follow their parent into PostgreSQL with no new grants.

### Negative

- A PostgreSQL database must be initialized before use, and again after an
  upgrade that changes the schema.
- Running the PostgreSQL tests needs a server, so they are skipped unless
  one is named.
- The credentials travel inside `AZATHOTH_DATABASE`, so the URL is a secret,
  and every process tool that grants it can read it, as it already could
  read the path.
- The SQL is limited to what both databases share.

## Alternatives Considered

### A separate PostgreSQL class per repository

Rejected. It would add as much code again as the SQLite repositories hold,
and the two would drift.

### SQLAlchemy

Rejected. Azathoth's SQL is small and portable, and an ORM would be a large
dependency for everyone, to save little of it.

### A separate variable for the URL

Rejected. A second variable would need a new grant in every tool that runs
`azathoth`, and would leave two variables to say which database is meant.

### Storing payloads as `JSONB`

Rejected. Exact content is part of a record's identity; queries into the
payload are not needed.

### Creating the PostgreSQL schema whenever a repository opens

Rejected. Every command of every container would run DDL against a shared
database, and a later migration would race between them.

### Aurora Serverless Data API, or DynamoDB

Rejected. Both tie Azathoth to AWS, and neither runs on a laptop or in CI the
way PostgreSQL does.
