# Evaluation

`azathoth.evaluation` determines whether an actual result satisfies an expected outcome.

Evaluation is the canonical correctness boundary in Azathoth.

Execution records what happened.

Evaluation determines whether the observed result met the objective.

This separation keeps execution deterministic and reusable while allowing many evaluation strategies to coexist.

## Purpose

Execution answers:

> **What happened?**

Evaluation answers:

> **Was the result correct?**

These are intentionally different responsibilities.

A workflow may execute perfectly and still produce an incorrect answer.

Likewise, a strategy may produce the correct answer despite using a slower or more expensive model.

Evaluation measures correctness independently from execution quality.

## Expected Outcomes

An `ExpectedOutcome` describes what a reproducible example should produce.

```python
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)

expected = ExpectedOutcome(
    description="Return the correct greeting.",
    value="Hello, world!",
    comparison=OutcomeComparison.EXACT,
)
```

An expected outcome contains:

- a description;
- an expected JSON-compatible value; and
- the intended comparison method.

Expected outcomes are immutable.

They define success criteria for a single reproducible example.

## Comparison Types

Expected outcomes specify the kind of comparison required.

Current comparison categories include:

- `EXACT`
- `SEMANTIC`
- `SCHEMA`

```text
Expected Outcome
        │
        ▼
Comparison Type
        │
        ▼
Concrete Evaluator
```

The comparison type expresses intent.

Concrete evaluators implement the comparison behavior.

## Evaluator Protocol

Every evaluator implements the same asynchronous interface.

```python
from pydantic import JsonValue

from azathoth.evaluation import (
    EvaluationResult,
    ExpectedOutcome,
)


async def evaluate(
    expected: ExpectedOutcome,
    actual: JsonValue,
) -> EvaluationResult: ...
```

This common protocol allows deterministic evaluators, semantic evaluators, schema validators, and future model-assisted evaluators to coexist behind one interface.

## ExactMatchEvaluator

Azathoth currently includes `ExactMatchEvaluator`.

It performs deterministic strict equality.

```python
from azathoth.evaluation import ExactMatchEvaluator

evaluator = ExactMatchEvaluator()

result = await evaluator.evaluate(
    expected=expected,
    actual="Hello, world!",
)
```

The evaluator returns:

- a normalized score;
- pass/fail status;
- rationale; and
- structured evidence.

No heuristics are involved.

## EvaluationResult

Every evaluation produces an immutable `EvaluationResult`.

It records:

- evaluator name;
- evaluator version;
- normalized score;
- threshold;
- pass/fail status;
- rationale; and
- supporting evidence.

```text
EvaluationResult
├── Evaluator
├── Score
├── Threshold
├── Status
├── Reason
└── Evidence
```

Scores are normalized between:

```text
0.0 = worst
1.0 = best
```

The recorded status is automatically validated against the score and threshold to ensure internal consistency.

## Evaluation Evidence

Evaluators may include structured evidence supporting their conclusions.

For example, the exact-match evaluator records both:

```text
expected
actual
```

Future evaluators might instead include:

- similarity scores;
- schema validation failures;
- extracted fields;
- reasoning traces; or
- model confidence.

The evaluation model remains unchanged regardless of evaluator sophistication.

## Evaluation Is Not Scoring

This architectural boundary is extremely important.

Evaluation determines correctness.

Workflow scoring interprets correctness together with broader execution evidence.

```text
                EvaluationResult
                      │
                      │
                      ▼
              WorkflowScorer
               ▲    ▲    ▲
               │    │    │
               │    │    └── Cost
               │    └─────── Latency
               └──────────── Reliability
```

Evaluation asks:

> Was the answer correct?

Workflow scoring asks:

> Given correctness, reliability, latency, and cost, how good was this workflow overall?

Keeping these responsibilities separate allows multiple scoring policies to reuse the same evaluation evidence.

## Benchmark Datasets

Evaluation benchmarks define reusable workloads.

```text
BenchmarkDataset
├── BenchmarkCase
├── BenchmarkCase
└── BenchmarkCase
```

Each benchmark case contains:

- input;
- expected outcome; and
- optional metadata.

Benchmark datasets are immutable.

Evaluation infrastructure remains responsible only for determining whether
workflow outputs satisfy expected outcomes.

Benchmark execution belongs to the workflow layer.

### Benchmark Persistence

Reusable benchmark datasets can be persisted outside application source.

`BenchmarkRepository` provides the storage-neutral persistence boundary.

Current implementations include:

- `InMemoryBenchmarkRepository`; and
- `SQLiteBenchmarkRepository`.

```text
BenchmarkDataset
       │
       ▼
BenchmarkRepository
       │
       ├── InMemoryBenchmarkRepository
       └── SQLiteBenchmarkRepository
```

Repositories persist complete benchmark datasets, including:

- dataset identity;
- name;
- description;
- version;
- case identities;
- inputs;
- expected outcomes; and
- case metadata.

Persisting an existing dataset identifier is rejected rather than replacing the
stored workload.

### Benchmark Catalogs

`BenchmarkCatalogLoader` reconstructs an immutable `BenchmarkCatalog` from
repository state.

```text
BenchmarkRepository
       │
       ▼
BenchmarkCatalogLoader
       │
       ▼
BenchmarkCatalog
       │
       ▼
BenchmarkDataset
```

Repository order becomes catalog order.

Datasets can be selected by stable dataset identity.

### Reproducible Workloads

A persisted benchmark can be reconstructed after process restart with the same
version, case identities, inputs, and expected outcomes.

```text
persist dataset
      │
      ▼
process restart
      │
      ▼
reconstruct dataset
      │
      ▼
run same workload
```

Persistence preserves the benchmark definition.

Benchmark execution remains the responsibility of the workflow layer.

## Design Principles

Evaluation is intentionally:

- immutable;
- deterministic where possible;
- evidence based;
- provider independent;
- execution independent; and
- optimization independent.

Evaluators judge outcomes.

They do not execute strategies, rank workflows, or generate improved candidates.

## Typical Flow

```text
ExpectedOutcome
        │
        │
Actual Result
        │
        ▼
    Evaluator
        │
        ▼
EvaluationResult
```

Evaluation establishes objective correctness before higher-level scoring and optimization begin.

## Relationship to Other Packages

[`azathoth.goals`](../goals/README.md) defines the objectives that expected outcomes represent.

[`azathoth.execution`](../execution/README.md) produces the outputs evaluated by evaluators.

[`azathoth.workflows`](../workflows/README.md) combines evaluation results with execution evidence when producing workflow scorecards.

[`azathoth.optimization`](../optimization/README.md) uses evaluation results to compare competing strategies and workflows empirically.

See the [project README](../../../README.md) for the complete Azathoth architecture.