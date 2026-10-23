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
    SEMANTIC_EVALUATOR_NAME,
    SEMANTIC_EVALUATOR_VERSION,
    BenchmarkCase,
    BenchmarkCatalog,
    BenchmarkCatalogLoader,
    BenchmarkDataset,
    BenchmarkDocumentError,
    BenchmarkRepository,
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    Evaluator,
    EvaluatorMetadata,
    ExactMatchEvaluator,
    ExpectedOutcome,
    InMemoryBenchmarkRepository,
    InvalidJudgeResponseError,
    InMemoryJudgeRotationRepository,
    JsonDifference,
    JsonSchemaViolation,
    JudgeEntry,
    JudgeRotation,
    JudgeRotationRepository,
    NormalizedMatchEvaluator,
    OutcomeComparison,
    OutcomeEvaluator,
    SQLiteBenchmarkRepository,
    SQLiteJudgeRotationRepository,
    SchemaEvaluator,
    SemanticEvaluator,
    SemanticJudgingError,
    UnsupportedComparisonError,
    decode_benchmark_document,
    default_comparison_evaluators,
    encode_benchmark_document,
    expectation_hash,
    first_json_difference,
    json_schema_validator,
    json_schema_violations,
    json_type_name,
    judge_call_count,
    judge_calls_cost_usd,
    json_values_equal,
    normalize_json_value,
    normalize_text,
    parse_judge_verdict,
    require_benchmark_repository,
    require_judge_rotation_repository,
    semantic_judge_prompt,
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

For example, a schema expectation carries a JSON Schema as its value:

```python
ExpectedOutcome(
    description="Return the required support structure.",
    value={
        "type": "object",
        "properties": {
            "category": {"enum": ["billing", "technical", "account"]},
            "customer_message": {"type": "string"},
            "recommended_action": {"type": "string"},
        },
        "required": [
            "category",
            "customer_message",
            "recommended_action",
        ],
    },
    comparison=OutcomeComparison.SCHEMA,
)
```

What the value means depends on the comparison:

```text
exact / normalized
    the expected output itself

schema
    a JSON Schema the output must satisfy

semantic
    the expected meaning, judged by a language-model judge
```

# OutcomeComparison

`OutcomeComparison` identifies how an actual output is judged against an
expected outcome.

V1 defines:

```text
EXACT

NORMALIZED

SEMANTIC

SCHEMA
```

with serialized values:

```text
exact

normalized

semantic

schema
```

The comparison is declared per expected outcome, and therefore per benchmark
case.

```text
OutcomeComparison
    declares how one output is judged

Evaluator
    implements that judgment
```

Different cases in one benchmark may use different comparisons. A workflow
with conditional branches may legitimately produce an exact routing label for
one input and free text for another, and each case declares the standard its
own output must meet.

Comparisons belong to expected outcomes, never to workflows. Every workflow
judged against a case is held to that case's standard, so candidates cannot
choose or relax how they are judged.

# Schema Expectations Are Validated at Construction

When the comparison is `schema`, `ExpectedOutcome` rejects values that are not
valid JSON Schemas:

```text
Invalid JSON Schema: <reason>

A JSON Schema must be an object or a boolean.
```

Benchmark documents and CLI inputs construct `ExpectedOutcome`, so an invalid
schema is rejected at import rather than discovered during a run.

# OutcomeEvaluator

`OutcomeEvaluator` judges each expected outcome with the evaluator for its own
comparison:

```text
ExpectedOutcome.comparison
        │
        ├── exact       → ExactMatchEvaluator
        ├── normalized  → NormalizedMatchEvaluator
        ├── schema      → SchemaEvaluator
        └── semantic    → SemanticEvaluator, when judges are supplied
                          UnsupportedComparisonError, otherwise
```

It is the default evaluator for benchmark execution and configured workflow
optimization.

The delegated evaluator produces the result, so recorded evaluations name the
evaluator that actually judged the output (`exact-match`, `normalized-match`,
`json-schema`, `semantic-judge`), never the router.

The built-in mapping is returned by `default_comparison_evaluators()`. It
covers exact, normalized, and schema comparisons, and includes semantic
comparisons only when a semantic evaluator is supplied:

```python
OutcomeEvaluator(
    default_comparison_evaluators(
        semantic=SemanticEvaluator(
            rotation=rotation,
            models=judge_models,
        ),
    )
)
```

Callers may also supply their own mapping entirely.

# Unsupported Comparisons Are Rejected

A comparison with no evaluator raises `UnsupportedComparisonError`, a
`ValueError`:

```text
<subject> uses comparison 'semantic', which is not supported yet.
```

It is never judged by a substitute evaluator. Semantic comparisons are
unsupported whenever no semantic evaluator was supplied, which is how an
evaluator without judges rejects them.

`supports(comparison)` and `require_supported(comparison, subject=...)` let
callers check comparisons before doing any work. Benchmark execution checks
every case before executing any of them, and optimization checks every case of
its benchmark before generating any candidate, so unsupported work fails before
it starts rather than partway through.

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
    description="Compare expected and actual values using type-strict JSON equality.",
    version="2.0.0",
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

The built-in evaluators use:

```text
exact-match
    expected, actual, difference_path, expected_type, actual_type

normalized-match
    expected, actual, normalized_expected, normalized_actual,
    difference_path, expected_type, actual_type

json-schema
    schema, actual, violation_count, violations
```

Failure-only labels appear only when an output fails. Other evaluator
implementations may use different evidence appropriate to their judgment
method.

The generic `EvaluationResult` model remains stable.

# ExactMatchEvaluator

`ExactMatchEvaluator` performs deterministic, type-strict JSON equality between:

```text
expected.value

actual
```

Comparison follows JSON types rather than Python equality:

```text
booleans never equal numbers        true ≠ 1, false ≠ 0

null never equals other values      null ≠ false, 0, "", [], {}

numbers compare by value            1 = 1.0

arrays compare in order             [1, 2] ≠ [2, 1]

objects require identical keys      key order is irrelevant
```

The comparison is implemented by `first_json_difference()`, shared with the
normalized evaluator.

# Exact Match Pass

If the values are equal under JSON typing, the evaluator returns:

```text
score = 1.0

threshold = 1.0

status = PASSED
```

# Exact Match Failure

Otherwise it returns:

```text
score = 0.0

threshold = 1.0

status = FAILED
```

with a reason naming where the values first differ:

```text
Actual value did not exactly match expected value at $.intent.
```

No fuzzy matching or normalization is performed.

# Exact Match Supports Structured JSON

Nested objects and arrays are compared recursively.

The first difference is located by a `$`-rooted path:

```text
$                   the root value

$.result.approved   an object member

$.labels[1]         an array element
```

Object members are visited in sorted key order, so the same pair of values
always reports the same path. A length or key-set mismatch is reported at the
containing array or object.

# ExactMatchEvaluator Evidence

Every exact-match result records:

```text
expected = expected.value

actual = actual
```

A failure also records:

```text
difference_path = first differing path
```

and, when the JSON types differ there:

```text
expected_type = JSON type expected

actual_type = JSON type found
```

JSON type names are `null`, `boolean`, `number`, `string`, `array`, and
`object`.

# ExactMatchEvaluator Identity

The concrete evaluator reports:

```text
name = "exact-match"

version = "2.0.0"
```

Version `2.0.0` introduced type-strict comparison. Earlier results recorded
version `1.0.0`, when booleans could equal numbers, so recorded evaluations
show which rules judged them.

# Concrete Evaluators Do Not Dispatch on Comparison

Each concrete evaluator applies its own judgment without inspecting:

```text
expected.comparison
```

Comparison dispatch belongs to `OutcomeEvaluator`.

Using a concrete evaluator directly is an explicit choice to apply that
judgment regardless of the declared comparison.

# NormalizedMatchEvaluator

`NormalizedMatchEvaluator` applies type-strict JSON equality after normalizing
every string value.

Normalization is:

```text
NFKC Unicode normalization

case folding

NFKC normalization again

trim, and collapse internal whitespace runs to single spaces
```

The second normalization pass keeps case folding from reintroducing
non-canonical forms.

Therefore:

```text
"  Duplicate_Charge\n"   matches   "duplicate_charge"

"ＲＥＦＵＮＤ"              matches   "refund"

"Straße"                 matches   "strasse"
```

Normalization never relaxes structure:

```text
object keys are not normalized

array order still matters

inner spaces are not removed      "duplicate charge" ≠ "duplicatecharge"

types are not converted           "true" ≠ true, "1" ≠ 1
```

# NormalizedMatchEvaluator Evidence

Every result records:

```text
expected

actual

normalized_expected

normalized_actual
```

A failure also records `difference_path`, `expected_type`, and `actual_type`
exactly as exact matching does.

The evaluator reports:

```text
name = "normalized-match"

version = "1.0.0"
```

# SchemaEvaluator

`SchemaEvaluator` validates the actual output against the JSON Schema carried
as the expected value.

The schema dialect follows the schema's `$schema` keyword and defaults to
Draft 2020-12. Boolean schemas are valid: `true` accepts every value and
`false` rejects every value.

Validation is deterministic and offline:

```text
remote $ref values are never retrieved

format is an annotation, not an assertion

booleans never satisfy {"type": "integer"} or {"type": "number"}
```

# SchemaEvaluator Evidence

Every result records:

```text
schema

actual
```

A failure also records:

```text
violation_count = total violations

violations = up to ten {path, message} entries
```

Violations are ordered by path, then message, so the same output always
produces the same evidence:

```text
$.category   'shipping' is not one of ['billing', 'technical', 'account']

$.priority   9 is greater than the maximum of 5

$.tags[1]    3 is not of type 'string'
```

The evaluator reports:

```text
name = "json-schema"

version = "1.0.0"
```

# SemanticEvaluator

`SemanticEvaluator` judges whether an actual value means what the expected
value means. It is named `semantic-judge` and versioned `1.0.0`.

A language-model judge receives one fixed prompt containing the expectation's
description, the expected value as JSON, and the actual value as JSON. It must
reply with one JSON object and no other text:

```json
{"verdict": "pass", "reason": "<one sentence>"}
```

The verdict is binary, like every other comparison, so semantic results sit in
the same per-comparison pass counts as exact, normalized, and schema results:

```text
pass ──► score 1.0, threshold 1.0, PASSED
fail ──► score 0.0, threshold 1.0, FAILED
```

One surrounding Markdown code fence and surrounding whitespace are tolerated.
Anything else that is not a usable verdict, such as text that is not JSON,
a verdict other than lowercase `pass` or `fail`, or a missing or blank reason,
is an invalid reply.

# The Judge Rotation

Judges come from a durable, ordered `JudgeRotation` of `JudgeEntry` models,
each identified as `<provider>/<model>`. A rotation of one judge is valid.

The rotation is persisted through `JudgeRotationRepository` implementations,
`InMemoryJudgeRotationRepository` and `SQLiteJudgeRotationRepository`, which
keep judges in the order they were added and reject duplicates:

```text
Judge '<IDENTIFIER>' is already in the rotation.
Judge '<IDENTIFIER>' is not in the rotation.
```

# Judges Are Assigned Per Expectation

`rotation.judges_for(expected)` returns every judge in the order it should try
one expectation. The first judge is chosen by a stable hash of the expectation:

```text
sha256(canonical JSON of description, value, comparison) mod judge count
```

The rest follow in rotation order, wrapping around.

Assignment depends only on the expectation, never on the candidate or on call
order, so every candidate judged against the same benchmark case meets the
same judge first. Rankings compare candidates under the same judge rather
than letting judge-to-judge variance leak into the comparison.

The hash ignores object key order and is identical across processes and
platforms. Adding or removing a judge changes the judge count and therefore
reassigns cases, which is a configuration change like any other.

# Judge Fallback

A judge that raises, or replies without a usable verdict, is followed by the
next judge in its try order. The first usable verdict decides the evaluation.

```text
assigned judge ──► error or invalid reply
next judge     ──► usable verdict ──► evaluation
```

Every judge receives the identical prompt.

# Judging Failures Are Not Candidate Failures

When every judge fails, `SemanticEvaluator` raises `SemanticJudgingError`, a
`ValueError`, naming every attempt:

```text
Semantic judging failed with every judge: <judge> raised RuntimeError: down; <judge> replied without a usable verdict: reply is not JSON.
```

A judging failure is an infrastructure failure of Azathoth itself, not of the
judged candidate. It is never recorded as a failed case: the command running
the benchmark stops instead, so a judge outage can never corrupt a ranking.

# SemanticEvaluator Evidence

A semantic evaluation records:

```text
expected        the expected value
actual          the judged value
judge           the judge whose verdict decided the evaluation
verdict         pass or fail
judge_reason    the judge's one-sentence reason
judge_calls     every call made, in order
```

Each judge call records its judge, its status (`verdict`, `invalid_response`,
or `error`), a detail for failed calls, and its usage: prompt, completion, and
total tokens, latency, and estimated cost. A call that raised before replying
records no usage and costs nothing.

`judge_call_count(evaluation)` and `judge_calls_cost_usd(evaluation)` read that
evidence. Both return zero for evaluations by any other evaluator.

# Judge Cost Is Not Candidate Cost

Judging is the cost of running Azathoth, not the cost of the workflow being
judged.

Judge calls are recorded only as evaluation evidence. They are never part of
a `WorkflowRun`, so they never enter a run's cost, a benchmark's total cost,
or any scorecard's latency or cost dimension. Benchmark results report them
separately as `judge_calls` and `judge_cost_usd`.

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

That belongs to the execution/orchestration layer using the benchmark. The
workflow layer delivers it as the canonical `workflow.input.received` event,
payload `{"input": <value>}`, the same event production invocations emit.

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
              ├── description
              ├── value
              └── comparison
```

This makes the workload self-contained with respect to what result is
expected and how it is judged.

Each case declares its own comparison. There is no benchmark-level default:
reading a case is always enough to know how it is judged.

`BenchmarkDataset.comparison_counts()` reports how many cases use each
comparison, in comparison declaration order, omitting unused comparisons.

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
                           │        │
                           │        ▼
                    ACTUAL VALUE  OutcomeEvaluator
                           │        │
                           ▼        ▼

             Evaluator for that comparison
             exact / normalized / schema
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

comparison declaration
    ≠
evaluator implementation

unsupported comparison
    ≠
silent substitute judgment

normalized equality
    ≠
type coercion

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
