# Evaluation

`azathoth.evaluation` defines Azathoth's correctness-judgment and reusable
benchmark architecture.

Execution records what happened.

Evaluation compares an observed value with an explicit expected outcome and
produces structured judgment evidence.

```text
ExpectedOutcome
       +
Actual Value
       │
       ▼
Evaluator
       │
       ▼
EvaluationResult
```

The core distinction is:

```text
execution
    records behavior

evaluation
    judges behavior
```

Evaluation does not execute strategies, orchestrate workflows, rank candidates,
or promote production behavior.

# Architectural Role

Evaluation sits between empirical execution evidence and higher-level scoring,
experimentation, and optimization.

```text
ExecutionResult
      │
      ▼
actual output
      │
      +
ExpectedOutcome
      │
      ▼
Evaluator
      │
      ▼
EvaluationResult
      │
      ▼
scoring / experiments / optimization
```

The package also defines reusable benchmark workloads:

```text
BenchmarkDataset
      │
      └── BenchmarkCase
              ├── input
              └── ExpectedOutcome
```

Those workloads can be persisted and reconstructed independently from the code
that eventually executes them.

# Public Surface

The V1 evaluation package exports:

```python
from azathoth.evaluation import (
    BenchmarkCase,
    BenchmarkCatalog,
    BenchmarkCatalogLoader,
    BenchmarkDataset,
    BenchmarkRepository,
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorMetadata,
    ExactMatchEvaluator,
    ExpectedOutcome,
    InMemoryBenchmarkRepository,
    OutcomeComparison,
    SQLiteBenchmarkRepository,
    require_benchmark_repository,
)
```

The package therefore has two related responsibilities:

```text
evaluation domain

benchmark workload definition
```

Benchmark definition belongs here because benchmarks carry expected outcomes.

Benchmark execution remains outside this package.

# ExpectedOutcome

`ExpectedOutcome` describes what a reproducible example is expected to produce.

It is immutable.

Conceptually:

```text
ExpectedOutcome
├── description
├── value
└── comparison
```

Example:

```python
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)

expected = ExpectedOutcome(
    description="Return the classified support intent.",
    value="duplicate_charge",
    comparison=OutcomeComparison.EXACT,
)
```

The expected value is JSON-compatible.

This allows expectations to describe both scalar and structured outputs.

# Structured Expected Values

Expected values are not limited to strings.

For example:

```python
ExpectedOutcome(
    description="Return the required support structure.",
    value={
        "required_fields": [
            "category",
            "customer_message",
            "recommended_action",
        ],
    },
    comparison=OutcomeComparison.SCHEMA,
)
```

The evaluation domain therefore supports structured evaluation intent even
when a particular concrete evaluator has not yet been implemented for every
comparison category.

# OutcomeComparison

`OutcomeComparison` identifies the broad comparison method appropriate for an
expected outcome.

V1 defines:

```text
EXACT

SEMANTIC

SCHEMA
```

with serialized values:

```text
exact

semantic

schema
```

This field expresses evaluation intent.

It does not itself execute comparison logic.

```text
OutcomeComparison
    declares comparison category

Evaluator
    implements comparison behavior
```

# Comparison Intent Is Not Evaluator Dispatch

V1 does not define a global evaluator registry or automatic dispatcher such as:

```text
OutcomeComparison.EXACT
        │
        ▼
automatically locate ExactMatchEvaluator
```

The caller supplies an `Evaluator`.

Therefore:

```text
ExpectedOutcome.comparison
    evaluation intent

Evaluator instance
    executable evaluation policy
```

remain separate concepts.

This keeps evaluator selection explicit.

# Evaluator Protocol

`Evaluator` is a structural asynchronous protocol.

A compatible evaluator exposes:

```text
metadata

async evaluate(expected, actual)
```

Conceptually:

```python
class Evaluator(Protocol):
    @property
    def metadata(self) -> EvaluatorMetadata: ...

    async def evaluate(
        self,
        expected: ExpectedOutcome,
        actual: JsonValue,
    ) -> EvaluationResult: ...
```

The protocol does not require inheritance from a shared evaluator base class.

Any implementation satisfying the contract can participate.

# Evaluation Is Asynchronous

`Evaluator.evaluate()` is asynchronous.

```python
result = await evaluator.evaluate(
    expected,
    actual,
)
```

This permits evaluation implementations that may eventually require
asynchronous resources while preserving one common interface.

The protocol itself remains provider-neutral.

# EvaluatorMetadata

Every evaluator exposes immutable `EvaluatorMetadata`.

It contains:

```text
name

description

version
```

Example:

```python
EvaluatorMetadata(
    name="exact-match",
    description="Compare expected and actual values using equality.",
    version="1.0.0",
)
```

The metadata gives completed evaluation evidence stable evaluator identity.

# Evaluator Identity Becomes Evidence

When an evaluator produces an `EvaluationResult`, that result records:

```text
evaluator_name

evaluator_version
```

This lets later empirical systems distinguish:

```text
same candidate
evaluated by evaluator version A

from

same candidate
evaluated by evaluator version B
```

Evaluator identity is therefore part of the evidence.

# Evaluator Metadata Is Not Evaluation Result

These concepts remain separate:

```text
EvaluatorMetadata
    identifies evaluation behavior

EvaluationResult
    records one completed judgment
```

An evaluator may perform many evaluations while retaining the same stable
metadata.

# EvaluationResult

Every completed evaluation returns an immutable `EvaluationResult`.

Conceptually:

```text
EvaluationResult
├── id
├── evaluator_name
├── evaluator_version
├── score
├── threshold
├── status
├── reason
└── evidence
```

This is the core judgment artifact of the package.

# Evaluation Identity

Each `EvaluationResult` has an independent UUID.

```text
EvaluationResult.id
```

This identifies the completed judgment itself.

It is separate from evaluator identity.

```text
Evaluator
    identifies judging behavior

EvaluationResult
    identifies one judgment
```

# Normalized Score

`EvaluationResult.score` is normalized to:

```text
0.0 <= score <= 1.0
```

The evaluation domain rejects values outside that range.

The score represents the evaluator's normalized judgment.

The package does not assume every evaluator must produce only `0.0` or `1.0`.

For example, a valid result may contain:

```text
score = 0.86
```

# Threshold

Every result also records a normalized threshold:

```text
0.0 <= threshold <= 1.0
```

The default threshold is:

```text
1.0
```

Pass/fail semantics are:

```text
score >= threshold
    PASSED

score < threshold
    FAILED
```

# EvaluationStatus

V1 defines two statuses:

```text
PASSED

FAILED
```

serialized as:

```text
passed

failed
```

Status is not allowed to contradict score and threshold.

# Internal Result Consistency

`EvaluationResult` validates:

```text
expected_status =
    PASSED if score >= threshold
    else FAILED
```

If the supplied status disagrees, model construction fails.

For example:

```text
score = 0.0
threshold = 1.0
status = PASSED
```

is invalid.

This prevents contradictory evaluation evidence from entering higher-level
systems.

# Passed Property

`EvaluationResult.passed` is a convenience property derived from status.

```text
status == PASSED
      │
      ▼
passed == True
```

It does not recalculate evaluation policy independently.

# Reason

Every evaluation result requires a non-empty human-readable `reason`.

```text
reason
```

records the evaluator's explanation for its conclusion.

For example:

```text
Actual value exactly matched expected value.
```

or:

```text
Actual value did not exactly match expected value.
```

The reason supplements structured evidence rather than replacing it.

# EvaluationEvidence

An evaluator may attach zero or more immutable `EvaluationEvidence` items.

Each contains:

```text
label

value
```

where the value is JSON-compatible.

Conceptually:

```text
EvaluationResult
      │
      └── evidence
            ├── EvaluationEvidence
            ├── EvaluationEvidence
            └── ...
```

This gives evaluators a generic structured channel for explaining their
judgment.

# Evidence Is Evaluator-Defined

The evaluation domain does not impose one fixed evidence schema.

An evaluator chooses meaningful labels and structured values.

The exact-match evaluator uses:

```text
expected

actual
```

Other evaluator implementations may use different evidence appropriate to
their judgment method.

The generic `EvaluationResult` model remains stable.

# ExactMatchEvaluator

V1 provides one concrete evaluator:

```text
ExactMatchEvaluator
```

It performs deterministic Python equality between:

```text
expected.value

actual
```

Conceptually:

```text
expected.value
      │
      ▼
     ==
      ▲
      │
actual
```

# Exact Match Pass

If:

```text
expected.value == actual
```

then the evaluator returns:

```text
score = 1.0

threshold = 1.0

status = PASSED
```

# Exact Match Failure

If:

```text
expected.value != actual
```

then the evaluator returns:

```text
score = 0.0

threshold = 1.0

status = FAILED
```

No fuzzy matching or normalization is performed.

# Exact Match Supports Structured JSON

Because both expected and actual values are JSON-compatible, equality can
compare nested structures.

For example:

```text
{
    "intent": "duplicate_charge",
    "confidence": 0.97,
}
```

must equal the actual nested value exactly to pass.

A nested difference causes failure.

# ExactMatchEvaluator Evidence

Every exact-match result records:

```text
expected = expected.value

actual = actual
```

as two `EvaluationEvidence` items.

The completed result therefore carries both the conclusion and the direct
values used to reach that conclusion.

# ExactMatchEvaluator Identity

The concrete evaluator reports:

```text
name = "exact-match"

version = "1.0.0"
```

Those values are copied into every result it produces.

# ExactMatchEvaluator Does Not Dispatch on Comparison

The frozen V1 implementation compares:

```text
expected.value == actual
```

directly.

It does not branch on:

```text
expected.comparison
```

inside `ExactMatchEvaluator`.

Therefore callers should pair evaluator choice and expected comparison intent
coherently.

The package does not silently enforce or infer that pairing.

This is an important V1 boundary.

# Evaluation Is Not Execution

An evaluator receives:

```text
expected value

actual value
```

It does not execute the strategy that produced the actual value.

```text
Strategy
   │
   ▼
StrategyExecutor
   │
   ▼
ExecutionResult.output
   │
   ▼
Evaluator
```

Therefore:

```text
execution
    ≠
evaluation
```

The same recorded output may be evaluated multiple ways without rerunning the
strategy.

# Evaluation Is Not Strategy Behavior

A strategy does not decide whether its own output is correct.

```text
StrategyOutcome
    behavior evidence

EvaluationResult
    judgment evidence
```

This prevents executable candidates from marking themselves successful.

# Evaluation Is Not Workflow Reliability

A result can be correct even if execution required retries.

A result can be incorrect even if execution was operationally perfect.

Therefore:

```text
correctness
    ≠
reliability
```

Workflow-level scoring and statistics may combine these dimensions later.

# Evaluation Is Not Latency Measurement

Latency is execution evidence.

Evaluation score is correctness judgment.

```text
ExecutionResult.metrics.latency_ms
        ≠
EvaluationResult.score
```

An evaluator need not know how long execution took.

# Evaluation Is Not Cost Measurement

Likewise:

```text
estimated cost
```

belongs to execution metrics.

Evaluation does not decide whether the result was worth its cost.

```text
correctness
    ≠
cost efficiency
```

# Evaluation Is Not Workflow Scoring

This distinction is especially important.

Evaluation asks:

```text
How well did the observed output satisfy this expected outcome?
```

Workflow scoring may ask:

```text
Given quality, reliability, latency, and cost,
how strong was this workflow overall?
```

Conceptually:

```text
EvaluationResult
       │
       ├─────────────┐
       │             │
       ▼             ▼
 correctness    execution evidence
       │             │
       └──────┬──────┘
              ▼
       workflow scoring
```

Evaluation supplies one empirical dimension.

It is not the complete scorecard.

# Evaluation Is Not Ranking

An evaluator judges one actual output against one expectation.

It does not compare candidates against one another.

```text
candidate A evaluation
candidate B evaluation
candidate C evaluation
        │
        ▼
ranking layer
```

Therefore:

```text
evaluation
    ≠
ranking
```

# Evaluation Is Not Optimization

The evaluation package does not:

```text
generate new candidates

change model selection

rewrite prompts

select cheaper models

choose an experiment winner

promote production behavior
```

Optimization consumes evaluation evidence.

It does not live inside evaluation.

# BenchmarkCase

`BenchmarkCase` defines one reusable evaluation workload example.

It is immutable.

Conceptually:

```text
BenchmarkCase
├── id
├── input
├── expected
└── metadata
```

Its input is JSON-compatible.

Its expected value is an `ExpectedOutcome`.

Its metadata is optional structured JSON-compatible data.

# Benchmark Input

`BenchmarkCase.input` represents the reproducible input associated with the
example.

The evaluation package stores that input.

It does not define how a workflow must convert that value into runtime
execution context.

That belongs to the execution/orchestration layer using the benchmark.

# Benchmark Expected Outcome

Every case carries:

```text
ExpectedOutcome
```

directly.

```text
BenchmarkCase
      │
      ├── input
      └── expected
```

This makes the workload self-contained with respect to what result is expected.

# Benchmark Case Metadata

A case may contain arbitrary structured metadata such as:

```text
difficulty

domain

category
```

The evaluation package stores that metadata but does not interpret it as
ranking or execution policy.

# BenchmarkDataset

`BenchmarkDataset` is an immutable ordered collection of reusable benchmark
cases.

Conceptually:

```text
BenchmarkDataset
├── id
├── name
├── description
├── version
└── cases
```

The dataset provides stable identity and versioning for a reproducible
evaluation workload.

# Benchmark Dataset Identity

A benchmark dataset has:

```text
id

version
```

as distinct concepts.

The UUID identifies the durable dataset artifact.

The version describes the configured workload version.

# Case Identity Must Be Unique

A benchmark dataset rejects duplicate case UUIDs inside the same dataset.

```text
case A id = X

case B id = X

        ✗
```

This prevents ambiguous case identity inside a workload.

# Benchmark Order Is Preserved

Cases are stored as an ordered tuple.

```text
case 1

case 2

case 3
```

The dataset does not sort or reorder them.

A reconstructed workload can therefore preserve deterministic declaration
order.

# BenchmarkCatalog

`BenchmarkCatalog` is an immutable inventory of configured benchmark datasets.

```text
BenchmarkCatalog
└── datasets
```

It preserves dataset order and can resolve a dataset by UUID.

```text
dataset id
    │
    ▼
BenchmarkCatalog.get()
```

Unknown identities return `None`.

# BenchmarkRepository

Reusable benchmark datasets may be persisted through the storage-neutral
`BenchmarkRepository` protocol.

It defines:

```text
save(dataset)

get(dataset_id)

datasets()
```

The repository stores complete immutable `BenchmarkDataset` objects.

It does not execute them.

# Benchmark Repository Implementations

V1 provides:

```text
InMemoryBenchmarkRepository

SQLiteBenchmarkRepository
```

Both preserve datasets as durable configuration.

Persisting a duplicate dataset identity is rejected rather than silently
replacing the existing workload.

This gives benchmark datasets append-oriented durable identity semantics.

# BenchmarkCatalogLoader

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
```

Repository order becomes catalog order.

The loader does not execute benchmark cases or choose evaluators.

# Benchmark Persistence

Persistence preserves:

```text
dataset identity

dataset name

dataset description

dataset version

case identities

case inputs

expected outcomes

case metadata
```

This allows a benchmark workload to survive process restart as the same
configured evaluation artifact.

# Benchmark Definition Is Not Benchmark Execution

The evaluation package defines the workload.

It does not run a workflow against every case.

```text
BenchmarkDataset
    workload definition

workflow / experiment runner
    workload execution
```

This separation is important because executing a benchmark requires runtime
composition beyond the evaluation domain.

# Reproducible Benchmark Lifecycle

Conceptually:

```text
BenchmarkDataset
      │
      ▼
BenchmarkRepository
      │
      ▼
process restart
      │
      ▼
BenchmarkCatalogLoader
      │
      ▼
BenchmarkCatalog
      │
      ▼
selected BenchmarkDataset
      │
      ▼
higher-level runner executes cases
      │
      ▼
Evaluator judges outputs
```

Persistence reconstructs the workload.

Execution and evaluation remain explicit subsequent steps.

# Evaluation and Goals

Goals express broader desired objectives.

`ExpectedOutcome` represents the concrete expected result for one reproducible
example.

Conceptually:

```text
Goal
    broad objective

BenchmarkCase / OptimizationExample
    concrete example

ExpectedOutcome
    expected result for that example
```

The evaluation package does not infer an expected outcome automatically from a
goal.

# Evaluation and Execution

The standard empirical path is:

```text
Strategy
   │
   ▼
ExecutionResult
   │
   ▼
output
   │
   +
ExpectedOutcome
   │
   ▼
Evaluator
   │
   ▼
EvaluationResult
```

Execution and evaluation can therefore evolve independently.

# Evaluation and Workflows

Workflow infrastructure can evaluate workflow outputs and retain evaluation
evidence alongside workflow execution evidence.

The workflow domain may then construct richer artifacts such as:

```text
WorkflowRunEvaluation

WorkflowScorecard

WorkflowRanking
```

Those artifacts belong to the workflow domain.

The core evaluation package remains responsible for the generic judgment
vocabulary.

# Evaluation and Optimization

Optimization depends on empirical evidence.

```text
candidate
   │
   ▼
execute
   │
   ▼
actual output
   │
   ▼
evaluate
   │
   ▼
EvaluationResult
   │
   ▼
experiment / scoring / ranking
   │
   ▼
optimizer
```

The optimizer does not need to contain evaluator implementation logic.

It consumes completed evidence produced earlier in the pipeline.

# Evaluation Is Provider-Neutral

The generic evaluation domain contains no provider concepts.

`Evaluator.evaluate()` receives:

```text
ExpectedOutcome

JsonValue actual
```

not:

```text
LanguageModel

ModelResponse

OpenRouter client

provider metadata
```

A future evaluator could internally use a model, but the evaluator protocol
would remain provider-independent.

# Evaluation Result Is Not Production Authority

A passing evaluation does not deploy anything.

```text
EvaluationResult
    empirical judgment

WorkflowProductionState
    production execution authority
```

No evaluator may silently turn its judgment into active production state.

Promotion remains an explicit workflow operation.

# Evaluation Result Is Not Candidate Identity

An evaluation identifies:

```text
the evaluator

the completed judgment
```

It does not by itself identify the workflow candidate that produced the actual
value.

Higher-level experiment and workflow evidence owns the association between:

```text
candidate identity

execution evidence

evaluation evidence
```

This prevents generic evaluation models from becoming coupled to workflow
architecture.

# Complete V1 Evaluation Architecture

```text
                        EXPECTATION

                    ExpectedOutcome
                  ┌───────┼────────┐
                  │       │        │
                  ▼       ▼        ▼
            description  value  comparison
                           │
                           │
                    ACTUAL VALUE
                           │
                           ▼

                       Evaluator
                  ┌────────┴────────┐
                  │                 │
                  ▼                 ▼
          EvaluatorMetadata   evaluate(...)
                  │                 │
                  └────────┬────────┘
                           ▼

                   EvaluationResult
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
            score        status       evidence
              │            ▲
              ▼            │
           threshold ───────┘


                     BENCHMARK LAYER

                   BenchmarkDataset
                           │
                           ▼
                     BenchmarkCase
                    ┌──────┴──────┐
                    ▼             ▼
                  input     ExpectedOutcome
                           │
                           ▼
                 BenchmarkRepository
                           │
                           ▼
                BenchmarkCatalogLoader
                           │
                           ▼
                    BenchmarkCatalog
```

# V1 Evaluation Principles

The V1 evaluation architecture can be summarized as:

```text
execution
    ≠
evaluation

expected outcome
    ≠
evaluator implementation

comparison intent
    ≠
automatic evaluator dispatch

score
    ≠
status chosen independently

correctness
    ≠
reliability

correctness
    ≠
latency

correctness
    ≠
cost

evaluation
    ≠
workflow scoring

evaluation
    ≠
ranking

evaluation
    ≠
optimization

benchmark definition
    ≠
benchmark execution

passing evaluation
    ≠
production promotion
```

The central rule is:

```text
Execute first.

Judge explicitly.

Preserve the judgment as evidence.

Let higher layers decide what that evidence means.
```

That keeps Azathoth's correctness model reusable, reproducible, and independent
from the systems that execute candidates or make optimization and deployment
decisions.