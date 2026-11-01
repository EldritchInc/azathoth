# Workflows

`azathoth.workflows` defines the durable, executable, empirical, and production
lifecycle of an Azathoth workflow.

A workflow moves through distinct representations rather than allowing one
object to accumulate configuration, runtime state, experimental evidence, and
production authority.

```text
WorkflowSpecification
        │
        │ generation
        ▼
WorkflowCandidate
        │
        │ execution
        ▼
WorkflowRun
        │
        ├──────────────► evaluation / feedback / experiments
        │
        └──────────────► optimization
                                │
                                ▼
                         WorkflowCandidate
                                │
                                │ explicit promotion
                                ▼
                     WorkflowProductionState
                                │
                                │ production invocation
                                ▼
                           WorkflowRun
```

The separation between these representations is intentional.

## Workflow Specification

`WorkflowSpecification` is durable workflow intent.

It contains workflow metadata, an ordered collection of
`WorkflowStepSpecification` values, and an optional declared result.

A specification describes what the workflow is allowed and expected to do. It
is not itself an executable runtime instance and does not contain empirical
execution state.

Workflow specifications may be persisted through `WorkflowRepository`
implementations, including:

- `InMemoryWorkflowRepository`
- `SQLiteWorkflowRepository`

They can also be serialized and reconstructed through:

- `encode_workflow_document`
- `decode_workflow_document`

## Workflow Result

`WorkflowSpecification.result` declares which value is the workflow's answer.

It is a `WorkflowResultReference`, in one of two forms.

An explicit `WorkflowValueReference` names one producer step and one output:

```json
"result": {
  "producer_step_id": "22222222-2222-2222-2222-222222222222",
  "name": "answer"
}
```

The explicit reference is validated when the specification is constructed:

- the producer must be a step in the same workflow
- the name must be an output declared by that step

Violations fail with:

```text
Workflow result must reference a producer step in the same workflow.
Workflow result must reference an output declared by the producer step.
```

A name-only `WorkflowNamedValueReference` names the output alone, for workflows
whose answer can come from redundant producers:

```json
"result": {
  "name": "answer"
}
```

At least one step must declare an output with that name:

```text
Workflow result must name a value declared by at least one workflow step.
```

A name-only result resolves to the first step, in workflow step order, that
actually produced the value. Producers that were skipped, or that failed under
a tolerant failure policy, are passed over. Step order is chosen over
first-to-finish so the answer is reproducible.

The declared result is the single value that the rest of the lifecycle treats
as the workflow's outcome:

```text
declared result
      │
      ├── benchmark cases judge it
      ├── optimization experiments judge it
      └── promotion emits it as the production "result"
```

`workflow_result(run, reference, steps=...)` extracts the declared value from a
`WorkflowRun`. The steps are the workflow's steps in step order, which a
name-only result needs to choose among its producers.
`workflow_result_produced` reports whether any candidate producer produced it.

It fails with `WorkflowResultError` when the value was not produced, or when an
explicitly referenced step produced it more than once:

```text
Workflow result 'answer' from step <STEP_ID> was not produced.
Workflow result 'answer' from step <STEP_ID> was produced more than once.
Workflow result 'answer' was not produced by any workflow step.
```

`WorkflowCandidate.result` carries the declared result into each executable
candidate. Candidate generation copies it from the specification, and
candidates validate it against their own steps.

The domain field is optional so that workflows stored before results existed
still decode. Operations that need an answer reject a workflow without one
explicitly rather than guessing which output matters.

## Workflow Steps

A workflow is composed from `WorkflowStepSpecification` values.

Steps may be prompt-backed or tool-backed.

Prompt-backed steps carry prompting strategy configuration and model-selection
intent.

Tool-backed steps reference durable tool capability rather than embedding
process-local executable implementations.

Steps can additionally describe:

- dependencies
- input bindings
- output bindings
- conditions
- retry policy
- failure policy
- a message
- value emission

These properties form durable workflow topology and policy.

They are distinct from execution evidence.

### Step Messages

A step may declare a `message`, what it tells whoever is watching the
workflow when it starts, and may set `emit_values` to also emit its declared
values once it succeeds:

```json
"message": "Counting words with the process tool",
"emit_values": true
```

A step without a message is silent. Only a step with a message may emit
values, and only if it declares outputs:

```text
Workflow step <STEP_ID> emits values but declares no message.
Workflow step <STEP_ID> emits values but declares no outputs.
```

Both fields are presentation only. They never change how the step executes,
is evaluated, or is optimized. A step that leaves them unset serializes
without them, so existing documents and their content digests are unchanged.
Setting a message is a content change, so it makes a new revision.

Candidate generation carries both fields onto `WorkflowCandidateStep`, for
configured and production candidates alike.

## Candidate Generation

`WorkflowCandidate` is an executable realization of a workflow specification.

Candidate generation resolves durable workflow intent against the process-local
runtime environment.

```text
WorkflowSpecification
        +
ModelCatalog
ModelPortfolio
LanguageModelRegistry
ToolResolver
ToolImplementationResolver
        │
        ▼
WorkflowCandidate
```

`generate_workflow_candidate` performs this generation.

Candidate generation can fail explicitly with `WorkflowGenerationError` when
durable intent cannot be resolved into an executable candidate.

A candidate retains workflow identity while binding individual workflow steps
to executable strategies.

`WorkflowCandidateSignature` provides deterministic executable candidate
identity for empirical comparison.

A candidate is not production state.

It represents one executable possibility.

## Workflow Execution

`WorkflowRunner` executes a `WorkflowCandidate`.

Execution produces a `WorkflowRun`.

```text
WorkflowCandidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

`WorkflowRun` is immutable empirical evidence of what happened.

It contains `WorkflowStepRun` values describing the observed execution of each
step.

Step execution status is represented by `WorkflowStepStatus`.

Retries and terminal failures are represented through:

- `WorkflowStepAttempt`
- `WorkflowStepFailure`

Execution evidence is distinct from workflow configuration.

Running a workflow does not modify the workflow specification to reflect what
occurred.

### Concurrent Layers

The runner groups steps into dependency layers. A step's layer comes after
every step it depends on.

The eligible steps of one layer execute concurrently:

```text
layer 0:  A ──┐
          B ──┼── run together, each with the same layer context
          C ──┘
                 │
                 ▼  commit A, B, C in declared order
layer 1:  D (depends on A, B, C)
```

A layer commits only after every one of its steps has finished. Commits always
follow declared step order, so the recorded `WorkflowRun` and its final
context are identical whatever order the steps finish in.

A `fail_workflow` failure does not cancel its siblings. They finish and are
recorded, then the run stops before the next layer. When several steps of one
layer fail under `fail_workflow`, the first in declared order is the failure
the run reports. Steps that are expected to fail, such as redundant producers,
use `continue`.

There is no concurrency limit inside a layer: the width of the specification
bounds it.

### Run Success

A run that completes has succeeded, even when steps whose failure policy
tolerates failure failed along the way. A run fails only when it halts: a
`fail_workflow` step failed and the run stopped.

```text
failure under continue or skip_dependents   run completes   succeeded
failure under fail_workflow                 run halts       failed
```

`WorkflowRun.halted` records whether the run halted, and
`WorkflowRun.halting_step_id` names the first `fail_workflow` failure in
declared order, the one the run reports. Tolerated failures still appear in
the run's statistics and reliability metrics.

Runs recorded before halting was recorded leave both fields unset and are
judged as before: failed when any step failed.

`run_recording_failures` returns the completed run, halted or not, and is what
configured runs, production invocations, and benchmarks use, so every
executed run is persisted as evidence. `run` additionally raises the halting
step's failure.

### Observing Progress

`WorkflowRunner(observer=...)` reports step progress live to a
`WorkflowRunObserver`:

```text
WorkflowStepStarted    a step began its first attempt (once, never on retries)
WorkflowStepFinished   a step reached its final status, with its values or failure
```

Events arrive in the order steps actually start and finish, so concurrent
steps of one layer interleave. Skipped steps and steps whose inputs did not
resolve finish without starting. Each event carries the candidate step,
including its message and value emission.

Observation never changes recorded evidence. The runner discards anything an
observer raises, so a failing progress printer can never become a step
failure or cost a run its evidence.

## Values and Data Flow

Workflow data flow is explicit.

The workflow value model includes:

- `WorkflowInputBinding`
- `WorkflowValueBinding`
- `WorkflowValueReference`
- `WorkflowNamedValueReference`
- `WorkflowContextReference`
- `WorkflowConstantValue`
- `WorkflowValue`

Bindings describe declared data flow between workflow inputs, workflow steps,
and step outputs.

A step input's source takes one of four forms:

```json
{"producer_step_id": "<STEP_ID>", "name": "address"}
{"name": "address"}
{"event_type": "workflow.input.received", "field_name": "input"}
{"value": <JSON>}
```

The explicit form names exactly one upstream producer.

The name-only form resolves among the steps the consumer directly depends on
that declare an output with that name. The first of them, in workflow step
order, that actually produced the value supplies it. This lets redundant
producers in one layer race, with the consumer taking whichever survived:

```text
Primary  (continue) ──┐ address
Fallback (continue) ──┘ address
          │
          ▼
Consumer  input {"name": "address"}
```

At least one direct dependency must declare the name:

```text
Workflow input bindings must name a value declared by a step the consumer depends on.
```

The `workflow.input.bound` event recorded for every value input names the
producer that actually supplied it, so evidence always shows which redundant
producer was used.

### Constant Inputs

The fourth form binds a constant written in the workflow document (ADR 0094):

```json
{"name": "chapter_workflow_id", "source": {"value": "e1000000-0000-4000-8000-000000000040"}}
```

Any JSON value may be the constant, including objects, lists and `null`. A
constant has no producer, so it needs no dependency. The step receives it as
an ordinary bound input, recorded as:

```json
{"name": "chapter_workflow_id", "value": "e1000000-0000-4000-8000-000000000040", "constant": true}
```

Tools receive it as an input, and prompt variables bound to the input render
it. The source holds only `value`; a reference that also carries `value` is
rejected:

```text
A constant input source holds only 'value'.
```

Changing a constant changes the workflow document, so it is a new revision
and is promoted like any other change.

An output binding whose path does not resolve against a step's output fails
that attempt with `WorkflowValueResolutionError`:

```text
Cannot resolve workflow value 'count': missing object key 'count'.
```

It is retried under the step's retry policy, because a model may produce the
declared shape on a later attempt, and the step then fails under its own
failure policy instead of crashing the run.

### Prompt Steps Read Inputs by Name

A context-prompt step renders its declared inputs through
`PromptInputBinding`, which names the input to read:

```json
"inputs": [
  {"name": "plan", "source": {"producer_step_id": "<STEP_ID>", "name": "plan"}},
  {"name": "notes", "source": {"name": "notes"}}
],
"specification": {
  "template": {
    "text": "Plan: {plan}\nNotes: {notes}",
    "bindings": [
      {"variable_name": "plan", "input_name": "plan"},
      {"variable_name": "notes", "input_name": "notes"}
    ]
  }
}
```

A template that binds an input the step does not declare is rejected when the
step is constructed. Non-string values reach the prompt as JSON.

A prompt step that declares `"output_format": "json"` outputs its parsed
reply, so its output bindings may read fields of it by path.

### Unresolved Inputs

An input can legitimately have no value when its step becomes eligible, for
example when every redundant producer failed under `continue`.

The step is then recorded as failed under its own failure policy rather than
aborting the run. It records one failed attempt carrying
`WorkflowInputResolutionError`, it is not retried because resolution is
deterministic, and its strategy is never executed:

```text
Workflow input 'x' could not resolve value 'y' from step <STEP_ID>.
Workflow input 'x' could not resolve value 'y' from any step it depends on.
Workflow context input 'x' could not resolve event type 'e'.
Workflow context input 'x' could not resolve field 'f' from event type 'e'.
```

Benchmarks therefore judge such a run as a `workflow-run-failure` case instead
of aborting.

## Conditions, Retries, and Failure Policy

Workflow control flow remains part of durable workflow intent.

Conditional execution is represented by:

- `WorkflowCondition`
- `WorkflowConditionOperator`

Condition evaluation failures are represented by
`WorkflowConditionEvaluationError`.

Retry behavior is represented by `WorkflowRetryPolicy`.

Before each retry, the runner waits the delay the policy assigns to that
attempt, applying the backoff multiplier and the maximum delay. A zero delay
retries immediately. Because layer steps run concurrently, one step's backoff
never delays its siblings.

Failure handling is represented by `WorkflowFailurePolicy`.

These policies affect execution but remain separate from the resulting
`WorkflowRun` evidence.

## Step Confidence

A step may name one of its declared outputs as its confidence (ADR 0098):

```json
"outputs": [{"name": "category", "path": ["category"]}, {"name": "confidence", "path": ["confidence"]}],
"confidence": "confidence"
```

A name the step does not declare makes the specification invalid. A step
without `confidence` serializes without it, so digests are unchanged.

On every attempt, after the outputs resolve, `step_confidence` checks the
value: a JSON number from 0 to 1, integers included, booleans refused.
Anything else fails the attempt with `WorkflowStepConfidenceError`, retried
under the step's retry policy like an output that does not resolve:

```text
Workflow step <STEP_ID> confidence 'confidence' must be a number from 0 to 1; got 1.5.
```

A step that succeeds records its confidence on its `WorkflowStepRun`, on its
`WorkflowStepFinished` event, and on every event it adds to the workflow's
context. Skipped and failed steps, and steps without a declared confidence,
record none.

Escalation is composed, not built in. A step that backs another up:

- is conditioned on the first step's confidence, for example `less_than` 0.8;
- produces the same output names;
- is declared before the first step in the workflow's step order.

A value read by name comes from the first step in declared order that
produced it (ADR 0080), so consumers get the escalation step's value when it
ran and the first step's when it was skipped. The escalation step is an
ordinary step, so optimization, production model resolution, usage guards and
cost evidence all apply to it unchanged.

A confidence is only as good as whatever reports it, and Azathoth does not
calibrate it. Benchmarks show whether an escalation threshold helps.

## Evaluation and Evidence

Workflow execution evidence can be evaluated independently of execution.

The workflow package includes:

- `WorkflowEvaluation`
- `WorkflowRunEvaluation`
- `WorkflowScorecard`
- `WorkflowReliabilityMetrics`
- `WorkflowRunStatistics`

Run evaluations can be persisted through
`WorkflowRunEvaluationRepository` implementations.

This allows execution and judgment to remain separate concerns.

```text
WorkflowRun
     │
     ▼
evaluation
     │
     ▼
WorkflowRunEvaluation
```

## Feedback

Observed workflow runs may receive explicit feedback through
`WorkflowRunFeedback`.

Feedback disposition is represented by `WorkflowRunFeedbackDisposition`.

Feedback persistence is provided by `WorkflowRunFeedbackRepository`
implementations.

Feedback is evidence associated with execution.

It does not silently mutate durable workflow configuration.

### Benchmark Cases From Runs

A recorded run becomes a benchmark case only deliberately, through
`workflows/benchmark_case_source.py`:

- `workflow_run_input(run)` returns the payload of the run's single
  `workflow.input.received` event, and raises `BenchmarkCaseSourceError` when
  the run received none or more than one.
- `latest_corrected_output(feedback)` returns the latest bad feedback that
  carries a corrected output, latest by `created_at` with ties going to the
  later record. Good feedback never supplies a value.
- `benchmark_case_from_run(run, *, comparison, expected, description=None,
  feedback=None)` builds a new case replaying the run's input. Its metadata
  names the source run under `SOURCE_RUN_METADATA_KEY` (`source_run_id`) and,
  when given, the feedback under `SOURCE_FEEDBACK_METADATA_KEY`
  (`source_feedback_id`). A schema comparison requires a valid JSON Schema.

## Experiments

Experiments compare executable workflow candidates using empirical execution
against a benchmark.

`WorkflowExperimentRunner.run(workflows=..., dataset=...)` runs every
candidate against every case of a `BenchmarkDataset`, judges each declared
result with the case's own comparison, combines each candidate's per-case
scorecards with `aggregate_workflow_scorecards`, and ranks the combined
scorecards.

The experiment model includes:

- `WorkflowExperimentEvidence`
- `WorkflowExperimentResult`
- `WorkflowExperimentCaseObservation`
- `WorkflowExperimentObservation`
- `WorkflowExperimentRecord`

Experiment records can be persisted through `WorkflowExperimentRepository`
implementations.

Before any candidate executes, the runner rejects an empty dataset, any
unsupported comparison, and any candidate without a declared result. Failed
runs are recorded and scored as failed cases; see "Failed Runs" below.

A durable record names its benchmark and holds one observation per candidate:

```text
WorkflowExperimentRecord
├── id                      shared with the in-memory WorkflowExperimentResult
├── benchmark_id            None for records written before benchmarks
├── observations
│   └── WorkflowExperimentObservation
│       ├── id
│       ├── workflow / candidate_signature
│       ├── scorecard       combined across cases
│       └── cases
│           └── WorkflowExperimentCaseObservation
│               ├── case_id         None when no benchmark case applied
│               ├── run_id
│               ├── evaluation_id
│               ├── passed          None for records written before cases
│               └── judge_calls / judge_cost_usd    0 for records written before them
├── ranking                 observation IDs, best first
└── recorded_at
```

`WorkflowExperimentEvidence` and each observation carry `judge_calls` and
`judge_cost_usd` beside the scorecard, and `WorkflowExperimentResult` totals
them over every candidate. They never enter a scorecard, so judging never
changes how candidates score or rank.

Run and evaluation IDs are unique across every case of every observation, and
the ranking covers every observation exactly once. `winner`,
`ranked_observations`, `observation(id)`, and `observation_for_run(run_id)`
navigate a record.

Records written before multi-case experiments decode unchanged: a `mode="before"`
validator turns each old single-run observation into one case without a case
ID, reusing the old run ID as the observation ID so the old run-ID ranking
still resolves.

Experiment results identify empirical winners without automatically changing
production state.

Selection and deployment remain separate operations.

## Scoring and Ranking

Workflow evidence can be converted into scorecards through:

- `WorkflowScorer`
- `WorkflowScoringPolicy`

Candidates can be ordered through:

- `WorkflowRanker`
- `WorkflowRanking`
- `RankedWorkflow`

Scoring and ranking describe empirical preference.

They do not confer production authority.

## Benchmarking

The workflow package also provides deterministic benchmark infrastructure for
comparing workflow candidates across benchmark cases.

The benchmark surface includes:

- `WorkflowBenchmarkRunner`
- `WorkflowBenchmarkScorer`
- `WorkflowBenchmarkRanker`
- `WorkflowBenchmarkComparator`
- `WorkflowBenchmarkResult`
- `WorkflowBenchmarkRanking`
- `WorkflowBenchmarkComparison`
- `WorkflowBenchmarkExecutionRecord`
- `WorkflowBenchmarkEvidenceRecorder`

Each case judges the workflow's declared result. Benchmarking a workflow
without a declared result fails before any case executes, and a successful run
that does not produce the result fails with `WorkflowResultError` naming the
case.

Each case's input enters the run's context as the canonical
`workflow.input.received` event, created by `create_workflow_input_event`.

## Failed Runs

`WorkflowBenchmarkRunner` executes cases with `run_recording_failures`, so a
`fail_workflow` failure never aborts a benchmark, a comparison, or an
experiment. Each run is then judged result first:

```text
declared result produced?
    yes ──► judged with the case's comparison, even if some steps failed
    no, and a step failed ──► evaluate_failed_run
    no, and no step failed ──► WorkflowResultError
```

A run that tolerated a failure but never produced its result is still judged
a run failure, even though the run itself succeeded.

Steps may fail by design under the `continue` and `skip_dependents` policies,
so a run that still produced its result is judged on it.

`evaluate_failed_run(run, expected)` returns a failing `EvaluationResult` from
the evaluator `workflow-run-failure` 1.0.0 with score `0.0`, naming the first
failed step and its final attempt's failure. It is persisted and rendered like
any other evaluation, and `WorkflowBenchmarkResult.run_failures` counts the
cases it judged.

`WorkflowScorer` gives a run judged this way no latency or cost credit, so a
crashing candidate never outranks a correct one on speed or price alone.

## Semantic Cases

Semantic cases are judged by whatever semantic evaluator the benchmark
runner's `OutcomeEvaluator` holds. A failed run on a semantic case never
reaches a judge; it is judged by `evaluate_failed_run` like any other.

`WorkflowBenchmarkResult` reports judging separately from the workflow:

- `judged_semantically`: whether any case used the semantic comparison
- `judge_calls`: every judge call recorded in the evaluations
- `judge_cost_usd`: their cost, never part of `total_cost_usd`

Each `WorkflowBenchmarkCaseResult` exposes the same facts per case:
`run_failure`, `judge_calls`, and `judge_cost_usd`.

`WorkflowBenchmarkResult.dataset_digest` and
`WorkflowBenchmarkComparison.dataset_digest` hold the content digest of the
exact benchmark revision executed. Saved execution and experiment records
carry it as `benchmark_digest`.

Benchmark results remain evidence.

They do not mutate configured or production workflow state.

## Benchmark Execution Records

A completed benchmark run or comparison can be saved as one
`WorkflowBenchmarkExecutionRecord`:

```text
WorkflowBenchmarkExecutionRecord
├── id                      shared with the WorkflowBenchmarkResult or Ranking
├── benchmark_id
├── benchmark_digest        content digest of the benchmark revision run
├── kind                    run | compare
├── candidates
│   └── WorkflowBenchmarkExecutionCandidate
│       ├── id
│       ├── workflow / candidate_signature
│       ├── scorecard       compare only
│       └── cases           one per benchmark case, in dataset order
│           └── WorkflowBenchmarkExecutionCase
│               ├── case_id / comparison
│               ├── run_id / evaluation_id
│               ├── passed / run_failure
│               └── judge_calls / judge_cost_usd
├── ranking                 candidate IDs, best first; compare only
├── scoring_policy          compare only
└── recorded_at
```

Run and evaluation IDs are unique across the record. A `run` record holds
exactly one candidate with no scorecard, ranking, or policy. A `compare`
record holds at least two scored candidates judged on the same case IDs in the
same order, its scoring policy, and a ranking covering every candidate
exactly once.

Candidates derive `cases_passed`, `accuracy`, `run_failures`,
`judged_semantically`, `judge_calls`, `judge_cost_usd`, and
`comparison_tallies`. Records derive `case_ids`, `ranked_candidates`,
`winner` (`None` for a run), total judge calls and cost, `candidate(id)`, and
`candidate_for_run(run_id)`.

Records persist through `WorkflowBenchmarkExecutionRepository`:

- `InMemoryWorkflowBenchmarkExecutionRepository`
- `SQLiteWorkflowBenchmarkExecutionRepository`

which save without replacing, and find executions by ID, by benchmark, by
workflow, and by run.

`WorkflowBenchmarkEvidenceRecorder(runs, evaluations, executions)` saves one
execution:

```text
record_run(result, *, candidate)
record_comparison(comparison, ranking, *, candidates, scoring_policy)
```

Each builds and validates the record before saving anything, then saves every
case run, every evaluation, and the record. Evidence that cannot form a valid
record leaves every repository unchanged.

## Production Promotion

Production promotion is explicit.

`promote_workflow_candidate` converts one explicitly selected executable
candidate into durable production intent.

```text
WorkflowSpecification
        +
WorkflowCandidate
        │
        ▼
materialize_workflow_candidate
        │
        ▼
WorkflowProductionState
```

Prompt-backed candidate model bindings are materialized as exact
`FixedModelSelection` values.

This prevents production behavior from silently depending on a future
portfolio-selection decision.

Promotion may additionally record explicit ordered model substitutions through
`WorkflowProductionModelSubstitution`.

Promotion requires a declared result. A workflow without one fails with
`WorkflowResultError` before anything is written:

```text
Workflow <WORKFLOW_ID> does not declare a result.
```

`materialize_workflow_candidate` also rejects a candidate whose result differs
from the specification's declared result.

Promotion persists two different forms of production information:

```text
WorkflowProductionState
    current production intent
    execution authority

WorkflowProductionRevision
    immutable deployment history
    audit evidence
```

These concepts must not be conflated.

## Production State

`WorkflowProductionState` is the durable description of what a workflow should
execute in production now.

It contains:

- the materialized production workflow specification
- explicit production model substitutions
- explicit production emissions

Production prompt steps must resolve to fixed model selections.

The state may permit ordered substitutes for a prompt step, but those
substitutes are explicitly authorized in production state.

There is no implicit portfolio failover during production execution.

## Specification Revisions

Workflow specifications are revisioned. The workflow ID is a lineage, and
`WorkflowRepository.save` appends a `WorkflowSpecificationRevision`:

```text
WorkflowSpecificationRevision
├── workflow_id
├── number            1, 2, 3 … per workflow
├── specification
├── content_digest    sha256 of the specification's canonical JSON
└── imported_at       None for specifications saved before revisions existed
```

`get` and `specifications` return the latest revisions; `latest_revision`,
`revision(id, number)`, and `revisions(id)` read history. Re-saving earlier
content appends a revision whose digest matches the earlier one, which
`earliest_identical_revision` names.

`SQLiteWorkflowRepository` stores revisions in
`workflow_specification_revisions` and, on opening a database written before
revisions, copies each `workflow_specifications` row in as revision 1.

The revision travels with everything executed from it:

```text
WorkflowCatalogLoader      WorkflowCatalog.revisions: latest number per workflow
generate_workflow_candidate(..., revision=)
WorkflowCandidate.revision
WorkflowCandidateSignature.workflow_revision
WorkflowRun.workflow_revision
WorkflowProductionState.specification_revision
```

Experiment and benchmark execution records hold signatures, so they name the
revision they judged. Every new field is optional, so records written before
revisions decode with `None`.

## Production Revisions

`WorkflowProductionRevision` records an immutable historical production
deployment.

Revisions can be persisted through
`WorkflowProductionRevisionRepository` implementations, including:

- `InMemoryWorkflowProductionRevisionRepository`
- `SQLiteWorkflowProductionRevisionRepository`

A revision is audit history.

It is not execution authority.

Production execution does not determine behavior by asking for the newest
revision or by following an active revision pointer.

Current execution behavior comes from `WorkflowProductionState`.

## Production Model Resolution

Production model resolution is deterministic and explicit.

For a prompt-backed production step:

```text
fixed primary model
        │
        ├── executable ──────► use primary
        │
        ▼
ordered explicit substitutes
        │
        ├── executable ──────► use first executable substitute
        │
        ▼
explicit failure
```

Resolution is provided by `resolve_production_model_selection`.

Relevant failures include:

- `ProductionPrimaryModelUnavailableError`
- `ProductionModelSubstitutesUnavailableError`

Production never silently expands its model authority beyond the models
recorded in production state.

## Production Invocation

`ProductionInvocation` records one external call against a workflow identity.

Its initial context records the caller's input twice, at the invocation's
creation time: as `production.invocation.received`, which invocation history
reads, and as the canonical `workflow.input.received` event that benchmark
cases also emit. A prompt bound to the workflow input therefore renders
identically when its workflow is optimized and when it is invoked.

It is created independently of any production revision identity.

The invocation service receives the workflow's active production state and
executes against that state.

```text
ProductionInvocation
        +
WorkflowProductionState
        │
        ▼
generate_production_workflow_candidate
        │
        ▼
WorkflowRunner
        │
        ▼
WorkflowRun
```

`invoke_production_workflow` coordinates this lifecycle.

The durable invocation result is represented by:

- `ProductionInvocationSuccess`
- `ProductionInvocationFailure`

Failure classification is provided by `ProductionInvocationErrorCode`.

## Invocation Idempotency

An invocation started through a job envelope (ADR 0097) records
`InvocationIdempotency`: the caller's idempotency key and the request digest
it was started with. An invocation started otherwise records none.

`invoke_production_workflow` takes `idempotency` and saves it with the
invocation before anything runs. A key is unique across recorded
invocations, whichever workflow they target: saving an invocation under a key
another one holds raises `IdempotencyKeyInUseError` and saves nothing, so of
two requests racing with one key, exactly one runs.

`ProductionInvocationRepository.invocation_for_idempotency_key(key)` finds
the invocation a key names. `validate_idempotency_key` holds the key rule: 1
to 255 characters, with no control characters.

`SQLiteProductionInvocationRepository` writes the key and digest to their
own `idempotency_key` and `request_digest` columns, with a unique index on
the key. A table from before ADR 0097 gains the columns in place, keeping
every invocation and its sequence.

Replay, conflict and resolution belong to the job envelope, in
`azathoth.jobs`, not to the invocation service.

## Invocation and Run Identity

Production invocation and workflow execution remain separately identifiable.

`ProductionInvocationRun` associates one production invocation with the
`WorkflowRun` that provides its empirical execution evidence.

This allows the system to retain both:

```text
external caller identity
        │
ProductionInvocation
        │
ProductionInvocationRun
        │
WorkflowRun
        │
empirical execution evidence
```

without collapsing the two concepts into one record.

## Production Emissions

A production workflow may explicitly declare caller-visible outputs using
`WorkflowProductionEmission`.

Production emissions reference declared workflow step outputs, explicitly or
by name alone. A name-only emission resolves exactly like a name-only result,
in the promoted specification's step order.

Promotion records exactly one emission, named by
`PRODUCTION_RESULT_EMISSION`:

```text
result <- declared workflow result
```

A production invocation therefore returns:

```json
{
  "result": <declared result value>
}
```

Keeping the answer under one named key leaves room for additional emissions
later without changing where callers find the result.

Production states promoted before declared results existed have no emissions
and return `{}`. Promoting the workflow again records the `result` emission.

`emit_production_result` projects completed workflow execution into the
declared production response.

An invalid declared emission fails explicitly with `ProductionEmissionError`.

Internal workflow execution evidence therefore remains richer than the
caller-visible production result.

## Persistence

The workflow package defines persistence contracts separately from domain
behavior.

Durable repositories include contracts for:

- workflow specifications
- workflow runs
- run evaluations
- feedback
- experiments
- current production state
- immutable production revisions
- production invocations
- invocation/run associations

Both deterministic in-memory implementations and SQLite implementations are
provided for the relevant repository contracts.

Repositories store domain state.

They do not own workflow orchestration, provider access, optimization policy,
or runtime composition.

## Architectural Boundaries

The V1 workflow architecture deliberately maintains the following separations:

```text
WorkflowSpecification
    durable configured intent

WorkflowCandidate
    executable realization

WorkflowRun
    immutable execution evidence

WorkflowEvaluation / WorkflowRunEvaluation
    judgment of evidence

WorkflowExperimentResult
    empirical comparison

WorkflowProductionState
    current durable production intent
    execution authority

WorkflowProductionRevision
    immutable deployment history

ProductionInvocation
    durable external production call
```

These boundaries allow configuration, execution, experimentation,
optimization, deployment, and production operation to evolve independently
without allowing historical evidence or process-local runtime state to become
implicit production authority.
