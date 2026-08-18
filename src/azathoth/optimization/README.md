# Optimization

`azathoth.optimization` provides the empirical optimization layer for Azathoth.

It contains the models, orchestration, ranking, workflow optimization contracts, and multi-generation session infrastructure used to compare candidate behavior and produce future candidate populations.

Optimization answers the question:

> Given reproducible evidence about competing candidates, what should be tried next?

It intentionally does not own low-level strategy execution or workflow execution.

## Purpose

Azathoth is designed around empirical optimization.

Instead of choosing prompts, models, strategies, or workflows based on intuition alone, Azathoth creates reproducible evidence:

```text
Candidate
    │
    ▼
Execute
    │
    ▼
Evaluate
    │
    ▼
Score
    │
    ▼
Compare
    │
    ▼
Optimize
```

The optimization package provides the abstractions required to make that process repeatable.

It currently supports two related optimization paths:

- strategy-level optimization using reproducible examples; and
- workflow-level optimization using workflow experiment evidence.

These paths share the same architectural philosophy while operating on different candidate types.

## Optimization Architecture

At a high level:

```text
                   azathoth.optimization

        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
Strategy Optimization                 Workflow Optimization
        │                                     │
OptimizationExample                   WorkflowExperimentResult
        │                                     │
OptimizationRunner                    WorkflowOptimizer
        │                                     │
OptimizationRun                       WorkflowOptimizationResult
        │                                     │
ExperimentRunner                      Optimization Session
        │                                     │
StrategyScorecard                     Generation History
        │
StrategyRanker
        │
StrategyRanking
```

Strategy optimization measures competing strategies against reproducible examples.

Workflow optimization consumes the richer experiment evidence produced by the workflow package and generates future workflow populations.

## OptimizationExample

`OptimizationExample` describes one reproducible optimization case.

It contains:

- an identifier;
- a name;
- a goal;
- an initial context;
- an expected outcome; and
- optional tags.

```python
from azathoth.context import Context
from azathoth.evaluation import (
    ExpectedOutcome,
    OutcomeComparison,
)
from azathoth.goals import Goal
from azathoth.optimization import OptimizationExample

example = OptimizationExample(
    name="exact-answer",
    goal=Goal(
        name="Return the expected result",
        description="Produce the required deterministic output.",
        success_criteria=("The output matches the expected value.",),
    ),
    context=Context(),
    expected_outcome=ExpectedOutcome(
        description="Return success.",
        value="success",
        comparison=OutcomeComparison.EXACT,
    ),
)
```

Optimization examples are immutable.

They allow several candidate strategies to be compared against exactly the same goal, context, and expectation.

## OptimizationRunner

`OptimizationRunner` executes and evaluates one strategy against one optimization example.

```text
OptimizationExample
        +
Strategy
        +
Evaluator
        │
        ▼
OptimizationRunner
        │
        ├── Strategy Execution
        └── Evaluation
        │
        ▼
OptimizationRun
```

Example:

```python
from azathoth.optimization import OptimizationRunner

run = await OptimizationRunner().run(
    example=example,
    strategy=strategy,
    evaluator=evaluator,
)
```

The runner composes existing execution and evaluation infrastructure.

It does not implement strategy behavior or evaluator logic itself.

## OptimizationRun

An `OptimizationRun` records the complete result of executing and evaluating one strategy against one example.

It contains:

- its own identifier;
- optimization example identifier;
- `ExecutionResult`;
- `EvaluationResult`;
- start time; and
- completion time.

```text
OptimizationRun
├── example_id
├── execution
├── evaluation
├── started_at
└── completed_at
```

The run also exposes whether the evaluation passed.

```python
if run.passed:
    ...
```

Optimization runs are immutable.

## Strategy Experiments

The optimization package includes `ExperimentRunner` for strategy-level experiments.

It executes every supplied strategy against every supplied optimization example.

```text
Examples
   +
Strategies
   +
Evaluator
   │
   ▼
ExperimentRunner
   │
   ▼
StrategyScorecards
```

Conceptually:

```text
Strategy A
├── Example 1
├── Example 2
└── Example 3

Strategy B
├── Example 1
├── Example 2
└── Example 3
```

Each strategy receives its own scorecard containing the complete set of evaluated runs.

## StrategyScorecard

`StrategyScorecard` aggregates optimization evidence for one strategy.

It contains:

- strategy metadata; and
- one or more optimization runs.

Derived properties include:

- run count;
- passed count;
- pass rate; and
- mean evaluation score.

```text
StrategyScorecard
├── StrategyMetadata
├── OptimizationRun
├── OptimizationRun
├── OptimizationRun
│
├── run_count
├── passed_count
├── pass_rate
└── mean_score
```

The scorecard validates that every recorded execution belongs to the strategy represented by the scorecard.

This prevents evidence from different strategies from being accidentally mixed.

## Strategy Ranking

`StrategyRanker` deterministically compares strategy scorecards.

```python
from azathoth.optimization import StrategyRanker

ranking = StrategyRanker().rank(scorecards)
```

The canonical ranking currently considers:

1. pass rate;
2. mean evaluation score;
3. run count;
4. strategy identifier; and
5. strategy version.

```text
StrategyScorecards
        │
        ▼
StrategyRanker
        │
        ▼
StrategyRanking
```

The additional identity-based tie breakers ensure deterministic ordering.

## RankedStrategy

Each ranked entry contains:

- its rank; and
- the corresponding strategy scorecard.

```text
RankedStrategy
├── rank
└── scorecard
```

Ranks are positive and consecutive.

## StrategyRanking

`StrategyRanking` contains the ordered comparison of strategy scorecards.

```python
winner = ranking.winner
```

The winner is the scorecard at rank one.

Ranking remains separate from experiment execution so alternative ranking behavior can evolve independently.

## Strategy Optimization Flow

The current strategy-level optimization flow is:

```text
Goal
 │
 ▼
OptimizationExample
 │
 ├── Context
 └── ExpectedOutcome
        │
        ▼
Candidate Strategies
        │
        ▼
OptimizationRunner
        │
        ▼
OptimizationRuns
        │
        ▼
ExperimentRunner
        │
        ▼
StrategyScorecards
        │
        ▼
StrategyRanker
        │
        ▼
StrategyRanking
        │
        ▼
Winner
```

This path provides empirical comparison of strategies without requiring workflow orchestration.

## Workflow Optimization

Workflow optimization begins after the workflow package has completed an experiment.

The workflow package owns:

- workflow specification;
- workflow candidate generation;
- execution;
- evaluation orchestration;
- scoring;
- ranking; and
- workflow experiments.

The optimization package begins at the next decision:

> What candidate population should be evaluated next?

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
WorkflowOptimizer
        │
        ▼
WorkflowOptimizationResult
```

This boundary prevents optimization algorithms from becoming coupled to workflow execution internals.

## WorkflowOptimizer

`WorkflowOptimizer` is the common protocol for workflow optimization algorithms.

```python
from typing import Protocol

from azathoth.optimization import WorkflowOptimizationResult
from azathoth.workflows import (
    WorkflowCandidate,
    WorkflowExperimentResult,
)


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

- the experiment evidence for the current population;
- the current executable candidate population; and
- the generation number being produced.

It returns the candidate population for the new generation.

## Why Experiment and Candidates Are Separate Inputs

`WorkflowExperimentResult` intentionally contains scorecards and ranking evidence rather than executable workflow candidates.

Optimization therefore receives both:

```text
Experiment Evidence
        +
Source Candidate Population
        │
        ▼
WorkflowOptimizer
```

This keeps experiment results focused on empirical evidence while still giving optimizers access to the executable candidates they may transform.

Future durable representations may provide stable candidate identity without
forcing live strategy objects into experiment evidence.

## WorkflowOptimizationResult

`WorkflowOptimizationResult` represents one optimizer-produced generation.

It contains:

- generation number;
- the previous workflow experiment; and
- the candidate population produced for the new generation.

```text
WorkflowOptimizationResult
├── generation
├── previous_experiment
└── candidates
```

Generation numbering begins at one.

```text
Generation 0
    = externally supplied initial population

Generation 1
    = first optimizer-produced population

Generation 2
    = second optimizer-produced population

...
```

The result is immutable.

## Runtime Candidate Artifacts

Workflow candidates contain executable strategy implementations.

Because those strategies are live runtime objects, workflow optimization results are currently runtime-facing artifacts rather than portable serialized workflow specifications.

Azathoth does not pretend that arbitrary executable Python strategy instances can be faithfully reconstructed from JSON.

A future durable candidate representation can provide serialization and provenance without weakening the runtime execution model.

## ReplayWorkflowOptimizer

`ReplayWorkflowOptimizer` is the first workflow optimizer implementation.

It intentionally performs no optimization.

```text
Current Candidates
        │
        ▼
ReplayWorkflowOptimizer
        │
        ▼
Same Candidates
```

Example:

```python
from azathoth.optimization import ReplayWorkflowOptimizer

result = ReplayWorkflowOptimizer().optimize(
    experiment=experiment,
    candidates=candidates,
    generation=1,
)
```

The result preserves:

- the experiment evidence;
- candidate order;
- candidate instances; and
- the requested generation number.

## Why Replay Exists

Replay optimization establishes the optimizer contract without introducing optimization heuristics.

That gives Azathoth a deterministic baseline capable of proving:

- package boundaries;
- population propagation;
- generation tracking;
- optimization orchestration; and
- multi-generation session behavior.

Only after these mechanics are trustworthy does adaptive optimization need to be introduced.

## Optimization Sessions

One optimization result represents one generation.

A `WorkflowOptimizationSession` records the entire optimization campaign.

```text
WorkflowOptimizationSession
├── initial_candidates
└── generations
    ├── WorkflowOptimizationResult 1
    ├── WorkflowOptimizationResult 2
    └── WorkflowOptimizationResult N
```

The session preserves:

- the initial externally supplied population; and
- every optimizer-produced generation.

Optimization sessions are immutable.

## Generation Invariants

Recorded generations must be consecutive and begin at one.

Valid histories include:

```text
()
(1)
(1, 2)
(1, 2, 3)
```

Invalid histories include:

```text
(2)
(1, 3)
(2, 3)
```

A session with no completed generations is valid as a model, representing an initialized campaign before optimization has begun.

The session runner itself requires at least one generation when executing a session.

## WorkflowOptimizationSessionRunner

`WorkflowOptimizationSessionRunner` orchestrates iterative optimization.

Its responsibility is deliberately small:

```text
Experiment
   │
   ▼
Optimize
   │
   ▼
New Population
   │
   └──────────────┐
                  │
                  ▼
              Experiment
```

Example:

```python
from azathoth.optimization import (
    WorkflowOptimizationSessionRunner,
)

session = await WorkflowOptimizationSessionRunner(
    experiment_runner=experiment_runner,
    optimizer=optimizer,
).run(
    initial_candidates=candidates,
    context=context,
    evaluator=evaluator,
    expected_outcome=expected,
    max_generations=5,
)
```

The session runner repeatedly:

1. runs an experiment over the current population;
2. gives the resulting evidence to the optimizer;
3. records the returned generation;
4. uses the returned candidates as the next population; and
5. repeats until the requested generation limit is reached.

## Population Propagation

Optimizer output becomes experiment input for the following generation.

```text
Initial Population
        │
        ▼
Experiment 0
        │
        ▼
Optimizer
        │
        ▼
Generation 1 Population
        │
        ▼
Experiment 1
        │
        ▼
Optimizer
        │
        ▼
Generation 2 Population
```

The session runner never assumes that optimizer output resembles its input.

The session runner does not assume that optimizer output is identical to its
input.

Optimizer-produced populations remain opaque to the orchestration layer as long
as they satisfy the public optimizer contract.

The orchestration layer remains unchanged.

## Experiment and Optimization Separation

This boundary is one of the most important in Azathoth.

Experiments ask:

> How did this population perform?

Optimizers ask:

> Given that evidence, what should the next population be?

```text
Experiment
   │
   │ evidence
   ▼
Optimizer
   │
   │ candidates
   ▼
Next Experiment
```

An experiment should not mutate candidates.

An optimizer should not execute workflows.

Keeping these concerns separate makes both independently testable and replaceable.

## Optimization Is Not Execution

The optimization package never needs to know how a strategy or workflow actually performs its work.

It consumes durable evidence produced by lower layers.

```text
Execution
    │
    ▼
Evaluation
    │
    ▼
Evidence
    │
    ▼
Optimization
```

This makes optimization compatible with future execution mechanisms without coupling optimization algorithms to them.

## Optimization Is Empirical

Azathoth's optimization philosophy is evidence-driven.

A candidate is not considered better because an optimizer claims it should be better.

It must be executed and measured.

```text
Generate Candidate
        │
        ▼
Execute Candidate
        │
        ▼
Evaluate Candidate
        │
        ▼
Compare Evidence
        │
        ├── improved → preserve signal
        │
        └── worse    → reject or deprioritize
```

Optimization proposes.

Experiments decide.

## Current Optimization Boundary

The current workflow optimization stack is intentionally conservative.

```text
Workflow Candidates
        │
        ▼
WorkflowExperimentRunner
        │
        ▼
WorkflowExperimentResult
        │
        ▼
ReplayWorkflowOptimizer
        │
        ▼
WorkflowOptimizationResult
        │
        ▼
WorkflowOptimizationSessionRunner
        │
        ▼
WorkflowOptimizationSession
```

The replay optimizer does not yet improve candidates.

This is deliberate.

The current infrastructure proves that the full iterative empirical loop works before introducing adaptive behavior.

## Cost-Aware Evidence

Execution evidence records estimated cost.

Workflow scorecards normalize cost relative to explicit targets.

```text
Quality
   ▲
   │
   │
   └────────► Cost
```

## Replaceable Optimizers

`WorkflowOptimizer` is the extension boundary for application-defined
optimization behavior.

```text
Experiment Evidence
        +
Current Population
        │
        ▼
WorkflowOptimizer
        │
        ▼
Next Population
```

Azathoth does not prescribe how an optimizer chooses the next population.

Applications may provide optimization implementations through this interface
without changing the deterministic execution, evaluation, scoring, ranking, or
experiment infrastructure.

Optimizer proposals receive no special trust. Improvement must be established by
subsequent execution and evaluation.

## Design Principles

The optimization domain is intentionally:

- empirical;
- deterministic around optimizer behavior where possible;
- immutable in its recorded artifacts;
- independent of execution internals;
- generation based;
- optimizer agnostic;
- evidence driven; and
- designed for replaceable optimization algorithms.

Optimization proposes future candidates.

It does not decide that those candidates are better merely because they were generated.

Improvement must be demonstrated through subsequent experiments.

## Complete Strategy Optimization Flow

```text
Goal
 │
 ▼
OptimizationExample
 │
 ▼
Candidate Strategies
 │
 ▼
OptimizationRunner
 │
 ▼
OptimizationRuns
 │
 ▼
ExperimentRunner
 │
 ▼
StrategyScorecards
 │
 ▼
StrategyRanker
 │
 ▼
StrategyRanking
 │
 ▼
Winner
```

## Complete Workflow Optimization Flow

```text
Workflow Specifications
        │
        ▼
Workflow Candidates
        │
        ▼
WorkflowExperimentRunner
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
Next Candidate Population
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

This loop provides the iterative empirical execution model exposed by the optimization package.

## Relationship to Other Packages

[`azathoth.goals`](../goals/README.md) defines the stable objectives represented by optimization examples.

[`azathoth.context`](../context/README.md) supplies reproducible execution state for optimization examples and workflow experiments.

[`azathoth.strategies`](../strategies/README.md) provides executable candidate behavior for strategy-level optimization.

[`azathoth.execution`](../execution/README.md) records the durable execution evidence consumed by optimization.

[`azathoth.evaluation`](../evaluation/README.md) determines whether candidate outputs satisfy expected outcomes.

[`azathoth.prompting`](../prompting/README.md) provides prompt-backed strategies that can participate in optimization.

[`azathoth.providers`](../providers/README.md) provides model metadata,
requirements, pricing, discovery, and executable model implementations used by
model-backed candidates.

[`azathoth.workflows`](../workflows/README.md) owns workflow execution, scoring, ranking, and experiments and supplies the evidence consumed by workflow optimizers.

See the [project README](../../../README.md) for the complete Azathoth architecture.