# ADR 0049: Persist Reusable Benchmark Datasets

- Status: Accepted
- Date: 2026-08-20

## Context

Azathoth uses benchmark datasets as reusable empirical workloads.

A benchmark dataset contains stable identity, versioned metadata, and a
collection of benchmark cases.

```text
BenchmarkDataset
├── id
├── name
├── description
├── version
└── cases
    ├── BenchmarkCase
    ├── BenchmarkCase
    └── BenchmarkCase
```

Each benchmark case contains:

```text
BenchmarkCase
├── id
├── input
├── expected outcome
└── metadata
```

`WorkflowBenchmarkRunner` executes every benchmark case against a workflow
candidate and evaluates the resulting workflow output against the expected
outcome stored in that case.

Benchmark datasets are therefore part of the empirical input to reproducible
workflow evaluation.

Before this decision, benchmark datasets had to be reconstructed through
application code each time a process started.

That prevented a versioned benchmark workload from being stored today and
executed unchanged after process restart.

## Decision

Azathoth persists reusable `BenchmarkDataset` artifacts through a
storage-neutral `BenchmarkRepository`.

```text
BenchmarkDataset
       │
       ▼
BenchmarkRepository
       │
       ├── InMemoryBenchmarkRepository
       │
       └── SQLiteBenchmarkRepository
```

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

Persistence remains below benchmark execution.

The benchmark runner consumes the same `BenchmarkDataset` domain object
regardless of whether it originated from application construction, memory,
SQLite, or another repository implementation.

## Durable Benchmark Identity

Each benchmark dataset has a stable UUID.

```text
BenchmarkDataset.id
```

Each benchmark case also has its own stable UUID.

```text
BenchmarkDataset
├── case A → case_id A
├── case B → case_id B
└── case C → case_id C
```

Persisting another dataset with the same identifier is rejected.

Benchmark persistence is append-only at this boundary.

## Dataset Versioning

Benchmark datasets include an explicit version.

```text
BenchmarkDataset
├── id
├── name
└── version
```

Version describes the stored benchmark workload.

Changing benchmark inputs, expectations, or workload semantics should produce
a deliberately distinct benchmark artifact rather than silently rewriting
historical benchmark meaning.

Stable benchmark identity and versioning allow experimental results to be
interpreted relative to the workload actually used.

## Benchmark Case Preservation

Persistence retains each benchmark case in full.

This includes:

- case identity;
- input;
- expected outcome;
- expected-outcome comparison behavior; and
- case metadata.

```text
Persisted BenchmarkCase
        │
        ├── input
        ├── expected
        └── metadata
```

This allows a reconstructed dataset to execute the same workload against the
same expected outcomes after process restart.

## Benchmark Catalogs

`BenchmarkCatalog` is an immutable inventory of configured benchmark datasets.

```text
BenchmarkCatalog
├── BenchmarkDataset A
├── BenchmarkDataset B
└── BenchmarkDataset C
```

Catalog order follows repository insertion order.

Datasets can be retrieved by stable dataset identity.

```text
BenchmarkRepository
        │
        ▼
BenchmarkCatalogLoader
        │
        ▼
BenchmarkCatalog.get(dataset_id)
```

The catalog does not execute benchmarks.

It provides deterministic access to reusable workload definitions.

## SQLite Representation

SQLite stores the canonical serialized benchmark dataset together with
queryable identity and descriptive metadata.

```text
benchmark_datasets
├── sequence
├── dataset_id
├── name
├── version
└── payload
```

The canonical domain payload is serialized through the benchmark model.

```text
BenchmarkDataset
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
BenchmarkDataset
```

`sequence` preserves insertion order.

`dataset_id` provides durable lookup identity.

`name` and `version` remain available as relational metadata.

Individual benchmark cases are not normalized into separate relational tables
because current benchmark execution consumes the reconstructed dataset as a
whole.

## Persistence Is Not Benchmark Execution

Benchmark persistence stores workload definitions.

Benchmark execution remains in the workflow layer.

```text
BenchmarkRepository
        │
        ▼
BenchmarkDataset
        │
        ▼
WorkflowBenchmarkRunner
        │
        ▼
WorkflowBenchmarkResult
```

The evaluation package defines benchmark inputs and expected outcomes.

The workflow package determines how workflow candidates are executed against
those inputs.

Persistence introduces no alternate benchmark execution path.

## Reconstructed Benchmark Execution

Durable benchmark datasets can be reconstructed alongside the other durable
configuration required for workflow execution.

```text
Persisted BenchmarkDataset
            +
Persisted WorkflowSpecification
            +
Persisted ModelMetadata
            │
            ▼
     reconstructed catalogs
            │
            ▼
     candidate generation
            │
            ▼
   WorkflowBenchmarkRunner
```

For every reconstructed benchmark case:

```text
BenchmarkCase
      │
      ▼
candidate_factory(case)
      │
      ▼
WorkflowCandidate
      │
      ▼
WorkflowRunner
      │
      ▼
workflow output
      │
      +
case.expected
      │
      ▼
Evaluator
```

The same benchmark case identity is retained in the resulting benchmark
evidence.

## Benchmark Inputs Drive Candidate Construction

`WorkflowBenchmarkRunner` supplies each `BenchmarkCase` to the configured
candidate factory.

This preserves a flexible boundary between benchmark data and workflow
construction.

```text
BenchmarkCase
      │
      ▼
candidate factory
      │
      ▼
WorkflowCandidate
```

The benchmark runner does not prescribe how benchmark input is represented
inside the candidate.

Applications remain free to bind benchmark case input into prompts, workflow
values, tool inputs, context, or another appropriate runtime representation.

## Benchmark Results Are Separate Evidence

This decision persists benchmark definitions.

It does not introduce persistence for `WorkflowBenchmarkResult`.

Benchmark results contain execution and evaluation evidence produced while
running a dataset.

```text
BenchmarkDataset
     durable input
          │
          ▼
WorkflowBenchmarkRunner
          │
          ▼
WorkflowBenchmarkResult
     derived evidence
```

Workflow runs and evaluator judgments already have independent durability
boundaries where durable evidence is required.

The reusable workload definition and the evidence produced from running it
remain separate concerns.

## Reproducibility

With durable benchmark datasets, Azathoth can preserve the complete workload
required to repeat an empirical measurement.

```text
TODAY

BenchmarkDataset
├── version
├── case identities
├── inputs
└── expected outcomes
        │
        ▼
      persist

════════ process restart ════════

      reconstruct
        │
        ▼
same BenchmarkDataset
        │
        ▼
run benchmark again
```

Persistence preserves what was asked and what result was expected.

Runtime execution may still produce different empirical results if models,
tools, provider behavior, or other runtime conditions differ.

Benchmark durability preserves the workload; it does not claim that external
runtime behavior is immutable.

## Consequences

### Positive

- Benchmark workloads survive process restarts.
- Benchmark case identities remain stable.
- Inputs and expected outcomes remain reproducible.
- Dataset versions remain durable.
- Benchmark catalogs can be listed and selected independently from application
  source.
- Workflow benchmark execution continues to use the existing runtime path.
- Benchmark persistence remains provider independent.
- Benchmark definitions remain independent from optimizer implementation state.

### Negative

- Applications must intentionally create new durable benchmark artifacts when
  workload semantics change.
- Persisted benchmark datasets may become stale relative to evolving product
  requirements.
- Runtime behavior may change even when the benchmark workload remains
  identical.
- SQLite stores benchmark cases inside the canonical JSON payload rather than
  normalizing them relationally.

## Alternatives Considered

### Reconstruct Benchmarks in Application Code

Rejected as the only mechanism.

A reusable benchmark should be capable of surviving process restart without
requiring the application to recreate its cases manually.

### Persist Individual Benchmark Cases Independently

Rejected for the current boundary.

Benchmark execution operates on a versioned `BenchmarkDataset`, and there is no
current case-level repository query requirement.

Persisting the dataset as the durable workload keeps its cases and version
together.

### Persist WorkflowBenchmarkResult Instead

Rejected as a substitute for dataset persistence.

A benchmark result records what happened during one execution.

It does not preserve a reusable workload that can be selected and executed
again later.

### Embed Runtime Workflow Candidates in Benchmark Datasets

Rejected.

Benchmark datasets describe reusable evaluation inputs and expected outcomes.

Executable workflow candidates are runtime artifacts produced independently
through candidate generation.

## Result

Azathoth can now persist a benchmark workload and execute that same workload
after process restart.

```text
BenchmarkDataset
       │
       ▼
BenchmarkRepository
       │
       ▼
 persistent storage
       │
       ▼
BenchmarkCatalogLoader
       │
       ▼
BenchmarkCatalog
       │
       ▼
WorkflowBenchmarkRunner
       │
       ▼
execution + evaluation evidence
```

Benchmark persistence stores reusable empirical workloads.

It introduces no workflow execution, model-selection, ranking, or optimization
policy.