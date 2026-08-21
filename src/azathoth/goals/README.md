# Goals

`azathoth.goals` defines what Azathoth is trying to accomplish.

Goals express desired outcomes independently from the strategies, prompts, models, workflows, or optimization algorithms used to achieve them.

## Purpose

Optimization requires a stable statement of intent.

Azathoth should be able to change:

- prompts;
- language models;
- strategies;
- workflow structures; and
- optimization algorithms

without changing the underlying objective.

The goal domain provides that stable boundary.

Goals describe **what success means**, not **how success is achieved**.

## Goal

A `Goal` represents one durable objective.

Each goal contains:

- a unique identifier;
- a name;
- a description;
- one or more success criteria; and
- optional constraints.

```python
from azathoth.goals import Goal

goal = Goal(
    name="Answer accurately",
    description="Produce the correct answer for the supplied request.",
    success_criteria=("The answer matches the expected result.",),
    constraints=("Do not rely on unavailable external state.",),
)
```

Goals are immutable.

Once created, they become stable reference points for experiments and optimization.

## Goal Persistence

Reusable goals can be persisted independently from application source.

`GoalRepository` provides the storage-neutral persistence boundary.

Current implementations include:

- `InMemoryGoalRepository`; and
- `SQLiteGoalRepository`.

```text
Goal
 │
 ▼
GoalRepository
 │
 ├── InMemoryGoalRepository
 └── SQLiteGoalRepository
```

Repositories persist complete immutable goals, including:

- stable identity;
- name;
- description;
- success criteria; and
- constraints.

Persisting an existing goal identifier is rejected rather than replacing the
stored objective.

### Goal Catalogs

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

Repository order becomes catalog order.

Goals can be selected by stable goal identity.

### Reusable Objectives

A persisted goal can be reconstructed after process restart and reused when
creating new optimization examples.

```text
persist Goal
    │
    ▼
process restart
    │
    ▼
reconstruct Goal
    │
    ▼
OptimizationExample
```

Goal persistence stores objective semantics.

It does not execute strategies or evaluate outcomes.

## Goals and Optimization Examples

A goal describes an objective.

An optimization example combines that objective with one reproducible scenario.

```text
Goal
 │
 ▼
OptimizationExample
 ├── Context
 └── ExpectedOutcome
```

Many optimization examples can share the same goal while exercising different contexts and expected outcomes.

This allows Azathoth to measure how well candidate strategies generalize across many situations while pursuing the same objective.

### Goal Snapshot Semantics

`OptimizationExample` continues to embed a complete immutable `Goal`.

A reusable goal may be reconstructed from a repository before creating the
example.

```text
GoalRepository
      │
      ▼
reconstructed Goal
      │
      ▼
OptimizationExample
      │
      └── embedded Goal snapshot
```

The example does not dynamically resolve its goal through the repository.

This preserves the exact success criteria and constraints under which the
example was defined, even if other goals are persisted later.

## Goals and Strategies

Goals deliberately know nothing about implementation.

```text
             Goal
          /    |    \
         ▼     ▼     ▼
 Strategy A  Strategy B  Strategy C
```

Multiple strategies may attempt to satisfy the same goal.

Future optimizers may generate entirely new strategies without requiring the goal itself to change.

This separation is fundamental to empirical optimization.

## Success Criteria

Success criteria describe the characteristics of successful behavior.

For example:

- answer correctly;
- remain factual;
- preserve formatting;
- satisfy required constraints; or
- produce valid structured output.

Success criteria are descriptive.

They do not contain executable evaluation logic.

Concrete evaluators determine whether an actual output satisfies an expected outcome.

## Constraints

Constraints describe requirements that should remain true while pursuing the goal.

Examples might include:

- do not exceed a latency budget;
- avoid unavailable tools;
- preserve user privacy;
- remain provider independent; or
- satisfy safety requirements.

Like success criteria, constraints are represented as immutable domain data.

Future planning and optimization systems can use them when selecting or generating candidate solutions.

## Design Principles

The goal domain is intentionally:

- immutable;
- provider independent;
- strategy independent;
- reusable across experiments;
- descriptive rather than procedural; and
- stable over time.

Goals define intent.

They do not execute behavior, evaluate outputs, or select implementations.

## Relationship to Other Packages

[`azathoth.context`](../context/README.md) provides the execution state used while pursuing goals.

[`azathoth.evaluation`](../evaluation/README.md) determines whether actual outputs satisfy expected outcomes derived from goals.

[`azathoth.strategies`](../strategies/README.md) provides executable behavior capable of pursuing goals.

[`azathoth.optimization`](../optimization/README.md) compares competing strategies and workflows attempting to satisfy the same goals across many reproducible examples.

See the [project README](../../../README.md) for the complete Azathoth architecture.