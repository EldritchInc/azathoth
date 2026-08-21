# ADR 0050: Persist Reusable Goals

- Status: Accepted
- Date: 2026-08-20

## Context

Azathoth models goals as immutable descriptions of desired outcomes.

A goal contains:

```text
Goal
├── id
├── name
├── description
├── success criteria
└── constraints
```

Goals describe intent.

They do not execute behavior, evaluate outputs, select strategies, or resolve
runtime implementations.

A single goal may be reused across many optimization examples, strategies,
experiments, and future optimization systems.

```text
             Goal
              │
      ┌───────┼───────┐
      ▼       ▼       ▼
 Example A Example B Example C
```

Before this decision, reusable goals had to be reconstructed in application
code after process restart.

That prevented canonical objectives from being selected and reused
independently from application source.

## Decision

Azathoth persists reusable `Goal` artifacts through a storage-neutral
`GoalRepository`.

```text
Goal
 │
 ▼
GoalRepository
 │
 ├── InMemoryGoalRepository
 └── SQLiteGoalRepository
```

`GoalCatalogLoader` reconstructs an immutable `GoalCatalog` from repository
state.

```text
GoalRepository
      │
      ▼
GoalCatalogLoader
      │
      ▼
GoalCatalog
      │
      ▼
Goal
```

Persistence stores declarative objective data only.

It introduces no strategy, evaluation, planning, or optimization behavior.

## Durable Goal Identity

Each goal has a stable UUID.

```text
Goal.id
```

Persisting another goal with the same identifier is rejected rather than
silently replacing the existing objective.

Goal persistence is append-only at this boundary.

## Complete Goal Semantics

Persistence retains the complete immutable goal definition.

```text
Goal
├── name
├── description
├── success criteria
└── constraints
```

Success criteria describe characteristics of successful behavior.

Constraints describe requirements that should remain true while pursuing the
goal.

Both remain descriptive domain data.

They do not become executable rules merely because the goal is persisted.

## Goal Catalogs

`GoalCatalog` is an immutable inventory of configured reusable goals.

```text
GoalCatalog
├── Goal A
├── Goal B
└── Goal C
```

Catalog order follows repository insertion order.

Goals may be retrieved by stable goal identity.

```text
GoalRepository
      │
      ▼
GoalCatalogLoader
      │
      ▼
GoalCatalog.get(goal_id)
```

The catalog does not select a goal automatically.

Applications decide which reusable objective should be used for a particular
example, workflow, experiment, or optimization process.

## SQLite Representation

SQLite stores the canonical serialized goal together with queryable identity
and descriptive metadata.

```text
goals
├── sequence
├── goal_id
├── name
└── payload
```

The canonical domain object round-trips through its own serialization.

```text
Goal
 │
 ▼
model_dump_json()
 │
 ▼
SQLite
 │
 ▼
model_validate_json()
 │
 ▼
Goal
```

`sequence` preserves insertion order.

`goal_id` provides durable identity.

`name` remains available as relational descriptive metadata.

Success criteria and constraints remain inside the canonical serialized goal
because current repository operations do not query them independently.

## Reconstructed Goals

A persisted goal can be reconstructed after process restart through the normal
catalog path.

```text
SQLiteGoalRepository
        │
        ▼
GoalCatalogLoader
        │
        ▼
GoalCatalog
        │
        ▼
Goal
```

The reconstructed goal is equal in value to the original immutable objective
but is a newly reconstructed domain object.

No separate persisted-goal runtime representation is introduced.

## Relationship to Optimization Examples

`OptimizationExample` embeds a complete `Goal`.

```text
OptimizationExample
├── id
├── name
├── goal
├── context
├── expected outcome
└── tags
```

Goal persistence does not change that model.

A reusable goal may be loaded from `GoalRepository` and then embedded into a
new optimization example.

```text
GoalRepository
      │
      ▼
reconstructed Goal
      │
      ▼
OptimizationExample
```

The optimization example therefore retains an immutable snapshot of the goal
semantics used when the example was created.

## Snapshot Semantics

Historical optimization examples do not resolve their goal dynamically through
`GoalRepository`.

This is intentional.

```text
GoalRepository
├── canonical Goal A
├── canonical Goal B
└── canonical Goal C

        select Goal B
              │
              ▼
OptimizationExample
└── embedded Goal B snapshot
```

Once constructed, the example retains the complete goal it was defined under.

Later repository changes or newly persisted goals do not silently alter the
meaning of existing examples.

## Reuse Across Examples

One reconstructed goal can seed many optimization examples.

```text
                 Goal
                  │
          ┌───────┴───────┐
          ▼               ▼
 OptimizationExample A   OptimizationExample B
 ├── Context A           ├── Context B
 └── Expected A          └── Expected B
```

The examples may exercise different contexts and expected outcomes while
preserving the same objective.

This supports empirical comparison across many situations without redefining
the goal itself.

## Persistence Is Not Goal Execution

A goal is descriptive.

```text
Goal
 │
 ├── success criteria
 └── constraints
```

Persistence does not turn these fields into executable behavior.

Concrete strategies still execute behavior.

Concrete evaluators still judge outputs.

Optimization systems may use goal semantics when deciding what to try, but
those decisions remain outside the goal persistence layer.

## Consequences

### Positive

- Reusable objectives survive process restarts.
- Goal identity remains stable.
- Success criteria remain reproducible.
- Constraints remain reproducible.
- Applications can list and select canonical goals independently from source
  code.
- One goal can seed many reproducible optimization examples.
- Historical optimization examples retain immutable goal snapshots.
- Goal persistence remains strategy independent.
- Goal persistence remains provider independent.
- Goal persistence introduces no optimizer implementation state.

### Negative

- Persisted goals may become stale relative to evolving product objectives.
- Changing goal semantics requires a deliberately distinct durable goal
  artifact rather than silent replacement.
- SQLite stores success criteria and constraints inside serialized JSON rather
  than normalized relational tables.
- Applications remain responsible for selecting which goal to use.

## Alternatives Considered

### Reconstruct Goals in Application Code

Rejected as the only mechanism.

A reusable objective should be capable of surviving process restart without
requiring the application to recreate it manually.

### Store Only Goal IDs in OptimizationExample

Rejected for the current model.

Optimization examples are intended to remain reproducible immutable artifacts.

Embedding the complete goal preserves the exact objective semantics under which
the example was defined.

### Dynamically Resolve Historical Examples Through GoalRepository

Rejected.

Repository changes must not silently alter historical example meaning.

### Persist Executable Goal Logic

Rejected.

Goals are descriptive domain data.

Evaluation and execution belong to other subsystems.

### Query Goals by Success Criteria or Constraints in SQLite

Rejected for the current persistence boundary.

The repository persists and retrieves reusable goals.

Search or semantic matching behavior should be introduced only when a concrete
application requirement justifies it.

## Result

Azathoth can now persist canonical reusable objectives and reconstruct them
after process restart.

```text
Goal
 │
 ▼
GoalRepository
 │
 ▼
persistent storage
 │
 ▼
GoalCatalogLoader
 │
 ▼
GoalCatalog
 │
 ▼
reconstructed Goal
 │
 ▼
OptimizationExample
```

Goal persistence stores what Azathoth is trying to accomplish.

It introduces no strategy execution, evaluator behavior, candidate generation,
or optimization policy.