# ADR 0041: Persistent Tool Repository

- Status: Accepted
- Date: 2026-08-17

## Context

Azathoth models tools as durable capabilities rather than application-specific
functions.

A tool consists of independently versioned artifacts including:

- tool definitions;
- executable implementations; and
- deterministic test cases.

Tool implementations already contain their runtime, entrypoint, and executable
source as data.

Tool definitions and implementations should therefore not require corresponding
Python modules inside the Azathoth source tree.

The existing tool catalogs are immutable execution snapshots and should remain
independent of mutable persistence infrastructure.

## Decision

Azathoth introduces a storage-neutral `ToolRepository` contract.

Repositories persist:

- `ToolDefinition`;
- `ToolImplementation`; and
- `ToolTestCase`.

An in-memory repository provides deterministic local and test behavior.

A SQLite-backed repository provides durable local persistence using the Python
standard library.

Persisted artifacts are append-only by identifier.

Attempting to save another artifact with an existing identifier is rejected
rather than replacing the existing record.

Repository contents are loaded into the existing immutable:

- `ToolCatalog`; and
- `ToolImplementationCatalog`.

Existing tool resolution, implementation resolution, execution, and verification
remain unchanged.

Tool catalogs do not know how persistence is implemented.

Tool resolvers do not query databases directly.

Tool executors do not depend on persistence.

## Persistence Model

SQLite stores each durable artifact as its canonical serialized Pydantic payload
together with its stable identifier and insertion order.

```text
SQLite
  │
  ├── tool_definitions
  ├── tool_implementations
  └── tool_test_cases
          │
          ▼
    ToolRepository
          │
          ▼
   ToolCatalogLoader
       /        \
      ▼          ▼
ToolCatalog   ToolImplementationCatalog
      │          │
      └────┬─────┘
           ▼
      Existing Resolvers
```

This avoids duplicating the complete domain model as a separate SQL schema.

## Consequences

### Positive

- Tool implementations no longer need to be compiled into Azathoth.
- Executable source can survive application restarts.
- Tool test cases survive application restarts.
- Existing immutable catalogs remain unchanged.
- Existing resolution and execution infrastructure remains storage agnostic.
- Historical implementations cannot be silently replaced by identifier.
- SQLite provides a zero-infrastructure persistence option for local development
  and demonstrations.
- Future persistence implementations can satisfy the same repository contract.

### Negative

- Persisted Pydantic payloads must remain compatible with future domain model
  evolution.
- SQLite schema evolution may eventually require explicit migrations.
- Persisted Python source is trusted code and still executes in process.
- Referential integrity between definitions, implementations, and test cases is
  not yet enforced by the repository.

## Alternatives Considered

### Store built-in tools as Python modules

Rejected because tools are intended to be durable, discoverable, versioned
artifacts rather than functions permanently compiled into the application.

A growing directory of application-specific tool implementations would also
make future tool synthesis and dynamic tool registration substantially harder.

### Make tool catalogs persistent

Rejected because catalogs represent immutable execution snapshots.

Persistence is mutable infrastructure.

Repositories load artifacts into catalogs rather than changing the catalog
abstraction.

### Query SQLite directly from tool resolvers

Rejected because resolution is a domain concern and should remain independent
of storage technology.

### Use SQLAlchemy

Rejected for the current implementation because standard-library SQLite is
sufficient for the current persistence requirements and avoids introducing an
additional dependency.

### Introduce PostgreSQL immediately

Rejected because the current goal is durable local tool storage and a
demonstrable execution path, not distributed persistence infrastructure.

## Future Direction

Persistent tools establish the foundation for future capabilities including:

- workflow tool execution;
- dynamic tool registration;
- implementation version history;
- persisted verification evidence;
- tool implementation benchmarking;
- tool ranking;
- synthesized tools; and
- optimizer-generated tools.