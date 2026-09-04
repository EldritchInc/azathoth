# Optimization

`azathoth.optimization` defines Azathoth's empirical optimization layer.

Optimization operates on evidence.

It does not decide that a workflow is better because an algorithm generated a
different candidate, and it does not silently deploy anything to production.

At the workflow level, the central optimization question is:

> Given empirical evidence about the current candidate population, what should
> Azathoth try next?

```text
WorkflowCandidate population
          │
          ▼
execution
          │
          ▼
evaluation
          │
          ▼
scoring
          │
          ▼
ranking
          │
          ▼
WorkflowExperimentResult
          │
          ▼
WorkflowOptimizer
          │
          ▼
next WorkflowCandidate population
```

The new population must itself be executed and evaluated before any claim of
improvement is justified.

## Architectural Boundary

Workflow optimization begins after `azathoth.workflows` has produced empirical
experiment evidence.

The workflow subsystem owns:

- workflow specifications
- workflow candidate generation
- workflow execution
- workflow evaluations
- workflow scoring
- workflow ranking
- workflow experiments

The optimization subsystem owns:

- resolving experiment evidence back to executable candidates
- producing future candidate populations
- optimization-generation results
- optimization sessions
- concrete optimization algorithms

```text
azathoth.workflows
        │
        ▼
WorkflowExperimentResult
        │
        ▼
azathoth.optimization
        │
        ▼
WorkflowOptimizationResult
```

This separation prevents optimization algorithms from becoming workflow
execution engines.

## Optimization Is Empirical

An optimizer proposes candidate behavior.

Evidence establishes whether that behavior is better.

```text
proposal
   │
   ▼
candidate
   │
   ▼
execute
   │
   ▼
evaluate
   │
   ▼
score
   │
   ▼
compare
```

Therefore:

```text
generated candidate ≠ improved candidate
```

and:

```text
optimizer opinion ≠ empirical result
```

A proposed candidate must survive the same execution and evaluation machinery
as every other candidate.

## WorkflowOptimizer

`WorkflowOptimizer` is the common protocol for workflow optimization
algorithms.

Conceptually:

```python
class WorkflowOptimizer(Protocol):
    def optimize(
        self,
        *,
        experiment: WorkflowExperimentResult,
        candidates: tuple[WorkflowCandidate, ...],
        generation: int,
    ) -> WorkflowOptimizationResult: ...
```

An optimizer receives:

- empirical evidence from the previous workflow experiment
- the executable candidate population that produced that evidence
- the generation number being produced

It returns a `WorkflowOptimizationResult`.

The optimizer does not execute the returned candidates.

## Why Evidence and Candidates Are Separate

`WorkflowExperimentResult` is empirical evidence.

`WorkflowCandidate` contains executable runtime behavior.

Those are deliberately different objects.

```text
WorkflowExperimentResult
        empirical evidence

WorkflowCandidate
        executable artifact
```

Optimization therefore receives both:

```text
experiment evidence
        +
source candidate population
        │
        ▼
WorkflowOptimizer
```

This allows experiment records to remain focused on observed results without
embedding live executable strategy objects inside the evidence model.

## Candidate Identity

Workflow experiment evidence identifies candidates through
`WorkflowCandidateSignature`.

The optimization package provides:

- `resolve_workflow_candidate`
- `resolve_workflow_experiment_evidence`
- `resolve_workflow_experiment_winner`

These functions reconnect empirical evidence with the executable candidate
population supplied to the optimizer.

```text
WorkflowExperimentEvidence
        │
        └── WorkflowCandidateSignature
                    │
                    ▼
            candidate resolution
                    │
                    ▼
             WorkflowCandidate
```

Resolution requires exactly one matching executable candidate.

Missing or ambiguous candidate identity fails explicitly.

## Empirical Winner Resolution

`resolve_workflow_experiment_winner` resolves the highest-ranked experiment
evidence back to the executable candidate that produced it.

```text
WorkflowExperimentResult
        │
        ▼
winner_evidence
        │
        ▼
WorkflowCandidateSignature
        │
        ▼
source population
        │
        ▼
winning WorkflowCandidate
```

This preserves a critical distinction:

```text
ranking evidence
    identifies the empirical winner

optimizer
    decides what to propose from that evidence
```

The optimizer does not independently redefine which candidate won the
experiment.

## WorkflowOptimizationResult

`WorkflowOptimizationResult` represents one optimizer-produced generation.

It contains:

- the generation number
- the previous experiment
- the candidate population produced for the new generation

```text
WorkflowOptimizationResult
├── generation
├── previous_experiment
└── candidates
```

Generation zero is the externally supplied initial population.

Optimizer-produced populations begin at generation one.

```text
Generation 0
    initial candidate population

Generation 1
    first optimizer-produced population

Generation 2
    second optimizer-produced population

...
```

The optimization result records what was proposed next.

It is not evidence that the proposal improved anything.

## Replay Optimization

`ReplayWorkflowOptimizer` is the deterministic baseline optimizer.

```text
current population
       │
       ▼
ReplayWorkflowOptimizer
       │
       ▼
same population
```

Replay preserves:

- the source experiment
- candidate identity
- candidate order
- the requested generation

Its purpose is to exercise optimization orchestration without changing
candidate behavior.

This provides a useful baseline for tests, application composition, and
multi-generation optimization sessions.

## Model Substitution Optimization

`ModelSubstitutionWorkflowOptimizer` provides V1's concrete adaptive workflow
optimization behavior.

Its optimization strategy is intentionally mechanical and explainable:

> Starting from empirically successful workflow behavior, try compatible models
> that are strictly cheaper.

At a high level:

```text
current candidate population
        │
        ▼
previous experiment
        │
        ▼
empirical winner
        │
        ▼
ModelSubstitutionWorkflowOptimizer
        │
        ├── preserve baseline candidate
        │
        └── generate cheaper substitutions
                    │
                    ▼
            next candidate population
```

The resulting substitutions are proposals.

Their quality is not assumed.

They must be evaluated in a subsequent experiment.

## Model Substitution Inputs

Model substitution operates using the existing provider and workflow
boundaries.

It receives:

```text
WorkflowSpecification
WorkflowCandidate
ModelCatalog
ModelPortfolio
LanguageModelRegistry
```

These provide distinct forms of authority:

```text
WorkflowSpecification
    durable workflow requirements

ModelCatalog
    current normalized model metadata

ModelPortfolio
    organizational selection authorization

LanguageModelRegistry
    executable implementations
```

Optimization does not collapse these concepts into a single model list.

## Eligible Model Substitutions

For prompt-backed workflow steps, model substitution considers models that:

1. satisfy the workflow step's declared model requirements;
2. are authorized by the `ModelPortfolio`;
3. exist in the current `ModelCatalog`;
4. have an executable implementation in the `LanguageModelRegistry`;
5. have comparable configured pricing; and
6. are strictly cheaper than the current model binding.

Conceptually:

```text
ModelRequirements
       +
ModelPortfolio
       +
ModelCatalog
       +
LanguageModelRegistry
       │
       ▼
eligible executable models
       │
       ▼
strictly cheaper models
```

Availability alone does not make a substitution eligible.

Authorization alone does not make a substitution executable.

## Strictly Cheaper

V1 model substitution uses a conservative Pareto pricing rule.

A target model is strictly cheaper when:

```text
target input price  <= current input price
target output price <= current output price
```

and at least one is strictly lower:

```text
target input price  < current input price
or
target output price < current output price
```

This avoids inventing assumptions about the relative number of input and output
tokens a particular workload will consume.

A model that is cheaper on input but more expensive on output is therefore not
automatically treated as cheaper.

## One-Step Candidate Mutation

Model substitution generates new workflow candidates by changing eligible model
bindings while preserving the rest of the executable workflow behavior.

Conceptually:

```text
winning candidate
      │
      ├── step A
      ├── step B
      └── step C
             │
             ▼
       replace one eligible
       model binding
             │
             ▼
      candidate variant
```

Each generated candidate remains a complete executable
`WorkflowCandidate`.

Optimization does not mutate the source candidate in place.

## Preserve the Baseline

The source candidate remains part of the next population.

```text
next population
├── baseline candidate
├── cheaper candidate A
├── cheaper candidate B
└── ...
```

This matters empirically.

A proposed cheaper model may reduce cost while also reducing quality,
reliability, or some other measured property.

Keeping the baseline allows the next experiment to compare the proposals
against known behavior rather than assuming every generated mutation is an
improvement.

## Expand From Empirical Evidence

Adaptive optimization is driven by the previous experiment.

The optimizer resolves the empirical winner and expands from that candidate
rather than treating every candidate in the previous population as equally
successful.

```text
previous population
       │
       ▼
experiment
       │
       ▼
ranking
       │
       ▼
winner
       │
       ▼
candidate expansion
```

This keeps candidate generation connected to measured performance.

## Workflow Optimization Sessions

`WorkflowOptimizationSessionRunner` coordinates iterative optimization across
multiple generations.

Conceptually:

```text
Generation 0 candidates
        │
        ▼
experiment
        │
        ▼
optimizer
        │
        ▼
Generation 1 candidates
        │
        ▼
experiment
        │
        ▼
optimizer
        │
        ▼
Generation 2 candidates
        │
       ...
```

The accumulated result is represented by `WorkflowOptimizationSession`.

A session provides the history of iterative empirical optimization rather than
only the final candidate population.

## Session Meaning

An optimization session records a sequence of:

```text
candidate population
        │
        ▼
empirical experiment
        │
        ▼
optimizer proposal
```

This history matters because optimization is not modeled as one opaque
transformation.

Each generation has evidence connecting it to the generation that follows.

## Strategy-Level Optimization

The optimization package also contains a lower-level empirical optimization
path for standalone strategies.

The strategy-level path uses:

- `OptimizationExample`
- `OptimizationRunner`
- `OptimizationRun`
- `ExperimentRunner`
- `StrategyScorecard`
- `StrategyRanker`
- `StrategyRanking`

Its flow is:

```text
Goal
 │
 ▼
OptimizationExample
 │
 ▼
candidate Strategies
 │
 ▼
OptimizationRunner
 │
 ▼
OptimizationRun
 │
 ▼
ExperimentRunner
 │
 ▼
StrategyScorecard
 │
 ▼
StrategyRanker
 │
 ▼
StrategyRanking
```

This path allows strategy behavior to be empirically compared without requiring
a complete workflow.

## OptimizationExample

`OptimizationExample` represents one reproducible strategy-level optimization
case.

It contains:

- identity
- name
- goal
- initial context
- expected outcome
- optional tags

The same example can be executed against multiple candidate strategies,
allowing them to be measured against equivalent conditions.

## OptimizationRunner

`OptimizationRunner` executes one strategy against one optimization example and
records the resulting optimization evidence.

It combines existing execution and evaluation boundaries rather than embedding
strategy-specific judgment inside the candidate.

## ExperimentRunner

The strategy-level `ExperimentRunner` runs candidate strategies across a
collection of optimization examples.

Conceptually:

```text
strategies × examples
       │
       ▼
OptimizationRun*
       │
       ▼
StrategyScorecard*
```

This creates a reproducible body of evidence for strategy ranking.

## Strategy Ranking

`StrategyRanker` orders strategy scorecards into a `StrategyRanking`.

Ranking is empirical comparison.

It does not modify strategies and does not deploy anything.

The strategy-level optimization surface therefore follows the same fundamental
principle as workflow optimization:

```text
execute first
measure second
compare third
change behavior afterward
```

## Optimization Is Not Execution

Workflow execution belongs to `azathoth.workflows`.

Strategy execution belongs to the existing execution/strategy boundaries.

An optimizer should not call itself evidence.

```text
WorkflowCandidate
       │
       ▼
WorkflowRunner
       │
       ▼
WorkflowRun
       │
       ▼
WorkflowExperimentResult
       │
       ▼
WorkflowOptimizer
```

The optimizer begins after empirical evidence exists.

## Optimization Is Not Evaluation

Optimization does not decide whether an output satisfies an expected outcome.

Evaluation produces that judgment.

Optimization consumes the resulting evidence.

```text
observed output
      │
      ▼
evaluation
      │
      ▼
evidence
      │
      ▼
optimization
```

Changing optimizer algorithms therefore does not require changing evaluation
semantics.

## Optimization Is Not Ranking

Workflow ranking belongs to the workflow experiment infrastructure.

Optimization consumes the ranking.

```text
WorkflowScorecards
        │
        ▼
WorkflowRanker
        │
        ▼
WorkflowRanking
        │
        ▼
WorkflowExperimentResult
        │
        ▼
WorkflowOptimizer
```

This prevents an optimizer from quietly redefining success in order to justify
its own proposals.

## Optimization Is Not Model Authorization

Model optimization operates within organizational authorization.

`ModelPortfolio` remains authoritative for models Azathoth may select during
general optimization.

```text
optimizer
   │
   ▼
ModelPortfolio
   │
   ▼
authorized search space
```

An optimization algorithm does not gain authority to execute arbitrary provider
models merely because they are discoverable.

## Optimization Is Not Production Authority

Optimization and production deployment are explicitly separate.

```text
WorkflowOptimizer
       │
       ▼
WorkflowOptimizationResult
       │
       ▼
candidate population
```

does **not** imply:

```text
WorkflowProductionState
```

Production state changes only through explicit promotion.

```text
selected WorkflowCandidate
        │
        ▼
explicit promotion
        │
        ▼
WorkflowProductionState
```

An optimizer may discover a candidate that appears empirically superior.

That does not authorize the optimizer to deploy it.

## Optimization Does Not Promote Winners

There is intentionally no automatic path:

```text
experiment winner
      │
      ▼
production
```

Instead:

```text
experiment winner
      │
      ▼
empirical evidence
      │
      ▼
explicit operator/application choice
      │
      ▼
promotion
      │
      ▼
WorkflowProductionState
```

This keeps optimization policy separate from deployment authority.

## Optimization Does Not Modify Active Production

A running optimization session does not mutate current production state.

These lifecycles may exist independently:

```text
ACTIVE PRODUCTION
WorkflowProductionState
        │
        ▼
production invocation
```

while simultaneously:

```text
EXPERIMENTATION
WorkflowCandidate population
        │
        ▼
experiments
        │
        ▼
optimization generations
```

Production remains stable until an explicit promotion replaces its durable
state.

## Optimization Is Replaceable

`WorkflowOptimizer` is the extension point for alternative optimization
algorithms.

An application may provide a different optimizer that proposes candidate
populations using another algorithm while keeping the rest of the empirical
stack unchanged.

```text
WorkflowExperimentResult
        +
current candidates
        │
        ▼
custom WorkflowOptimizer
        │
        ▼
next candidates
```

The optimizer may change.

The requirement for empirical validation does not.

## Runtime-Facing Candidate Artifacts

`WorkflowCandidate` contains executable strategy implementations.

Optimization results therefore operate on runtime-facing executable artifacts.

Azathoth does not pretend that arbitrary live Python strategy implementations
are automatically portable serialized configuration.

Durable workflow intent remains represented separately by
`WorkflowSpecification`.

This preserves:

```text
WorkflowSpecification
    durable intent

WorkflowCandidate
    executable realization

WorkflowOptimizationResult
    proposed executable generation
```

without weakening those boundaries for serialization convenience.

## Complete V1 Workflow Optimization Loop

The complete workflow optimization loop is:

```text
WorkflowSpecification
        │
        ▼
candidate generation
        │
        ▼
WorkflowCandidate population
        │
        ▼
WorkflowExperimentRunner
        │
        ├── execute
        ├── evaluate
        ├── score
        └── rank
        │
        ▼
WorkflowExperimentResult
        │
        ▼
WorkflowOptimizer
        │
        ▼
WorkflowOptimizationResult
        │
        ▼
next WorkflowCandidate population
        │
        ▼
WorkflowExperimentRunner
        │
        ▼
...
        │
        ▼
WorkflowOptimizationSession
```

Production remains outside this loop.

```text
optimization session
        │
        ▼
candidate chosen explicitly
        │
        ▼
promotion
        │
        ▼
WorkflowProductionState
```

## V1 Optimization Principles

The V1 optimization architecture follows these principles:

```text
evidence before optimization

candidate proposals are not trusted automatically

experiments determine observed performance

ranking remains separate from mutation

authorization bounds the model search space

executable candidates remain distinct from durable specifications

optimization remains distinct from production deployment
```

The central rule is:

> Azathoth may propose that something should be better. It must measure whether
> it actually is.

That rule allows optimization algorithms to become increasingly sophisticated
without giving those algorithms implicit authority over execution evidence,
organizational policy, or production behavior.