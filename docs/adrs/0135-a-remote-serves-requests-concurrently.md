# ADR 0135: A Remote Serves Requests Concurrently

- Status: Accepted
- Date: 2026-11-22

## Context

ADR 0124 served a remote one request at a time, behind one lock, since a
PostgreSQL database's repositories shared one connection. ADR 0127 noted
that this would not do once a remote serves the whole service API to a
team: a run, a benchmark or an optimization would hold up every other
request for as long as it read and wrote.

The single connection was not the only thing that kept requests apart. An
SQLite transaction began with `BEGIN IMMEDIATE`, taking the file's write
lock, so two reads also took turns. The server called its policy and its
audit on the event loop itself, so a plugin that read its database while
deciding held up every request, `/health` included. And a push was
checked against each lineage's latest revision before anything was
saved; one push at a time kept that check true until the save, and
nothing else did.

## Decision

### Transactions that only read

`Database.transaction(read_only=True)` begins a transaction that only
reads and takes no write lock. On SQLite it begins deferred, under
`PRAGMA query_only`; on PostgreSQL it begins `READ ONLY`. Either refuses
a write in it with `ReadOnlyTransactionError`, and it takes no `lock`.

Every method that only reads, in the repositories a remote serves,
reads in a read-only transaction: workflows and their production states,
tools, benchmarks, content, the model portfolio and the remote's tokens.
A test runs each path the protocol's routes read by over a database that
notes each transaction's kind, and finds only read-only ones.

### SQLite in WAL mode

An SQLite file is put in WAL mode the first time Azathoth opens it, and
keeps it. In WAL mode a reader sees what was committed when it began
reading, and neither waits for a writer nor makes one wait. Transactions
that may write still begin immediately, so processes that share a file,
such as the children of one map (ADR 0106), take turns rather than fail.

### A pool of PostgreSQL connections

A `PostgresDatabase` keeps a pool of up to eight connections, shared by
every repository over its URL and every thread of the process. Each
transaction borrows one and gives it back when it commits or rolls back.
Idle connections are kept; one found closed or broken is replaced, and
one whose commit or rollback failed is closed. A transaction that waits
thirty seconds and still finds every connection in use raises
`DatabaseBusyError`. `pool_size` and `wait_seconds` set both.

A transaction begun inside another on the same thread raises
`NestedTransactionError`, on either database: it would hold a connection
of its own, would not see the outer one's writes, and could wait on its
locks forever. Nothing in Azathoth nests one.

### Requests answered together

`RemoteServer` keeps no lock. Every call to a seam or a repository runs
off the event loop, in a thread, so a slow policy or a long push holds up
no other request. At most `max_concurrent` such calls run at once, eight
by default, as many as the pool holds connections, so threads never
outnumber connections. Each lineage of a push, pull or heads request is
decided in one call, stopping at the first refusal.

A remote calls its seams and its content store from several threads at
once. Each protocol says so, and Writing a Plugin says what that asks of a
plugin: keep no state two threads could change together, or guard it;
expect the factory to run once; keep every audit event. The core's own
fillers keep no state of their own.

### Pushes that build on the latest, checked as they save

Saving a workflow, tool version or benchmark takes `fast_forward`: the
revision must build on the lineage's latest, or on none when it has none,
and otherwise `NotFastForwardError` is raised and nothing is saved. The
SQL repositories check in the transaction that already holds the revision
table's write lock to number the revision, so no other revision is saved
between the check and the save, from another thread or another server.

A push saves each lineage's first new revision fast-forward only. Of two
pushes built on one latest revision, the second is told the lineage
diverged and to pull first, as if it had arrived later; one that loses
the race to the identical revision finds it held. A pull that forks still
forks.

### One server on an SQLite file

SQLite serves one remote process on one machine. Several processes on one
file queue every writer behind every other, and processes on several
machines, or a file on a network share, can corrupt it, since WAL needs
every process on the machine that holds the file. So `azathoth remote
serve` holds an exclusive lock on a file beside an SQLite database,
`<DATABASE>.serve-lock`, while it serves, and a second server on the same
file is refused before it serves anything, saying to use PostgreSQL for
more. The operating system releases the lock when the process ends,
however it ends. Other commands never take it, so they go on working
beside a server, and a PostgreSQL database takes none.

## Consequences

- A remote's requests read side by side, and a push or a run holds up
  only the writers of the tables it writes.
- A remote on PostgreSQL may run several server processes, on one machine
  or several, over one database, and pushes to one lineage from any of
  them never fork it silently.
- A remote on SQLite runs one server process. Its file gains `-wal` and
  `-shm` files beside it while it is open, and a `.serve-lock` file while
  it is served, which stays when the server stops.
- A plugin must be safe to call from several threads at once; the team
  tier's seams already open a transaction of their own for each call.
- A request may wait for a connection, and after thirty seconds is
  refused with `DatabaseBusyError`, where before it waited behind the
  lock without end.
- A push carrying several lineages still saves them one by one: when a
  later one has diverged, the earlier ones stay saved. Each is still
  never forked.

## Alternatives Considered

### One lock around each push

Holding a lock in the server around each push would keep the check of a
push true until its save, within one server. It would not hold between
two servers on one PostgreSQL database, which this decision makes the way
to serve more; checking in the transaction that saves holds for both.

### A pool from psycopg_pool

psycopg's own pool would have done the borrowing. It is another
dependency of the `postgres` extra, and the pool Azathoth needs is a few
dozen lines over the driver it already wraps, tested with the same
scripted driver as the rest.

### WAL only for a served file

Putting a file in WAL mode only when `azathoth remote serve` opens it
would leave single-person instances in the journal mode they had. But the
command line and the editor read while a run writes on any instance, and
WAL lets them; one mode for every file is also one less thing to explain.

### A note in place of the serve-lock

Saying in the documentation that SQLite serves one process would have
cost nothing. A second server on one file fails slowly, or corrupts it on
a network share, long after the note was skipped; refusing it at startup
costs one small lock.

### A limit per request, not per call

Bounding the requests in flight, rather than the calls to seams and
repositories, would let a request that makes several calls hold several
connections at once. Bounding the calls keeps the threads in use at most
the connections there are.
