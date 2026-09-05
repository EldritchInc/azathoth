# Goals

`azathoth.goals` defines Azathoth's durable objective model.

A goal describes what Azathoth is trying to accomplish independently from the
strategies, prompts, models, tools, workflows, evaluators, or optimization
algorithms used to pursue it.

```text
Goal
 │
 ├── success criteria
 └── constraints
```

The central architectural distinction is:

```text
objective
    ≠
implementation
```

Goals define intent.

They do not execute, evaluate, rank, optimize, or deploy behavior.

# Architectural Role

Azathoth changes executable behavior empirically.

The objective against which that behavior is considered should remain
independent from those implementation changes.

```text
                       Goal
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    Strategy A       Strategy B       Strategy C
```

Multiple strategies may pursue the same goal.

Likewise:

```text
                       Goal
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
    Workflow A       Workflow B       Workflow C
```

The goal does not need to change merely because the implementation used to
pursue it changes.

# Public Surface

The V1 goals package exports:

```python
from azathoth.goals import (
    Goal,
    GoalCatalog,
    GoalCatalogLoader,
    GoalRepository,
    InMemoryGoalRepository,
    SQLiteGoalRepository,
    require_goal_repository,
)
```

The package is intentionally small.

It defines:

```text
durable objectives

objective persistence

immutable objective catalogs
```

It does not contain execution, evaluation, or optimization machinery.

# Goal

`Goal` is the core domain object.

It is immutable.

Conceptually:

```text
Goal
├── id
├── name
├── description
├── success_criteria
└── constraints
```

Example:

```python
from azathoth.goals import Goal

goal = Goal(
    name="Answer accurately",
    description="Produce the correct answer for the supplied request.",
    success_criteria=(
        "The answer matches the expected result.",
        "The answer remains factual.",
    ),
    constraints=("Do not rely on unavailable external state.",),
)
```

# Goal Identity

Every goal has a stable UUID:

```text
Goal.id
```

If no UUID is supplied, one is generated.

Goal identity is separate from:

```text
name

description

success criteria

constraints
```

The ID identifies the durable objective artifact.

Names are descriptive rather than authoritative identity.

# Goal Name

`Goal.name` is a required non-empty descriptive name.

For example:

```text
Answer accurately
```

The name makes the objective understandable to people and application
interfaces.

It is not used as a substitute for stable UUID identity.

# Goal Description

`Goal.description` is a required non-empty description of the objective.

For example:

```text
Produce the correct answer for the supplied request.
```

The description provides broader intent than an individual success criterion.

It remains declarative domain data.

# Success Criteria

`Goal.success_criteria` is an ordered tuple of descriptive criteria associated
with successful behavior.

For example:

```text
The answer matches the expected result.

The answer remains factual.
```

A goal must contain at least one success criterion.

```text
Goal(
    success_criteria=(),
)

        ✗
```

The model rejects an empty success-criteria tuple.

# Success Criteria Are Required

This requirement means a goal cannot exist as only:

```text
name + vague description
```

without expressing at least one characteristic of success.

Conceptually:

```text
Goal
 │
 ▼
one or more success criteria
```

The goal domain therefore requires every durable objective to state something
about what successful behavior means.

# Success Criteria Are Descriptive

Success criteria are strings.

They are not executable predicates.

```text
"The answer remains factual."

        ≠

def evaluate_factuality(...):
    ...
```

The goal package does not interpret these strings at runtime.

It stores objective semantics.

# Success Criteria Are Not ExpectedOutcome

A goal's success criteria describe broad characteristics of successful
behavior.

An `ExpectedOutcome` describes the concrete expected result for one
reproducible example.

These concepts therefore have different scopes.

```text
Goal.success_criteria
    broad objective semantics

ExpectedOutcome
    expected result for one example
```

For example:

```text
Goal criterion:
    "Classify support requests correctly."

Example expectation:
    "duplicate_charge"
```

Many distinct expected outcomes may exist while pursuing the same goal.

# Success Criteria Are Not Evaluators

A success criterion does not determine how correctness is measured.

```text
success criterion
      │
      ▼
describes intent
```

while:

```text
Evaluator
      │
      ▼
executes judgment
```

The evaluator architecture remains separate.

This allows evaluation techniques to evolve without rewriting the underlying
goal.

# Constraints

`Goal.constraints` is an ordered tuple of descriptive requirements that should
remain true while pursuing the objective.

Constraints are optional.

The default is:

```text
()
```

Examples might include:

```text
Do not rely on unavailable external state.

Remain provider independent.

Preserve required output structure.
```

# Constraints Versus Success Criteria

Success criteria and constraints are deliberately distinct fields.

Conceptually:

```text
success criteria
    characteristics of succeeding

constraints
    conditions under which the objective should be pursued
```

For example:

```text
SUCCESS CRITERION

The answer matches the expected result.


CONSTRAINT

Do not rely on unavailable external state.
```

Both describe intent.

Neither is executable policy by itself.

# Constraints Are Descriptive

Like success criteria, constraints are strings.

The goal subsystem does not enforce them.

```text
Goal.constraints
      │
      ▼
durable descriptive intent
```

does not automatically become:

```text
runtime authorization

workflow failure policy

model filtering

tool filtering

production policy
```

Any subsystem that operationalizes a constraint must do so explicitly.

# Goal Is Immutable

`Goal` uses a frozen domain model.

Once constructed:

```python
goal.name = "Something else"
```

is invalid.

This supports stable empirical references.

If an objective's semantics materially change, callers should create the
appropriate new durable objective rather than mutating evidence retroactively.

# Goal Is Provider-Independent

The goal model contains no:

```text
provider

model

model identifier

model requirements

portfolio

language-model implementation
```

The same objective may therefore be pursued using different providers and
models.

```text
Goal
 ├── model A
 ├── model B
 └── model C
```

without making provider identity part of objective semantics.

# Goal Is Strategy-Independent

The goal model contains no `Strategy`.

```text
Goal
    ≠
Strategy
```

A goal states:

```text
what should be achieved
```

A strategy defines:

```text
executable behavior that may pursue it
```

This separation is fundamental to empirical comparison.

# Goal Is Workflow-Independent

Goals do not contain workflow topology.

They know nothing about:

```text
steps

dependencies

conditions

retries

value bindings

failure policy
```

A workflow may change substantially while still pursuing the same objective.

```text
Goal
  │
  ├── single-step workflow
  ├── multi-step workflow
  └── differently optimized workflow
```

The goal remains stable.

# Goal Is Evaluator-Independent

A goal contains no evaluator implementation.

This means the same goal can be investigated with different evaluation
techniques.

```text
Goal
 │
 ├── exact evaluation
 ├── semantic evaluation
 └── another evaluator
```

where appropriate concrete expectations and evaluators exist.

The goal itself remains descriptive.

# Goal Is Optimizer-Independent

A goal contains no optimization algorithm or optimizer state.

```text
Goal
    ≠
WorkflowOptimizer
```

An optimizer may change:

```text
candidate generation

model substitution

search strategy

generation policy
```

without changing the durable objective being pursued.

# Goal Is Not Production Authority

A goal describes desired behavior.

It does not decide what currently executes in production.

```text
Goal
    objective

WorkflowProductionState
    production execution authority
```

A goal cannot deploy a workflow.

A production state cannot redefine the goal merely by becoming active.

These remain separate domains.

# GoalRepository

Reusable goals may be persisted through the storage-neutral
`GoalRepository` protocol.

It exposes:

```text
save(goal)

get(goal_id)

goals()
```

Conceptually:

```text
Goal
 │
 ▼
GoalRepository
```

The repository stores complete `Goal` domain objects.

It does not interpret them.

# Repository Responsibilities

A goal repository owns:

```text
persistence

retrieval

ordered enumeration
```

It does not own:

```text
strategy execution

workflow execution

evaluation

optimization

goal selection policy
```

The repository is deliberately behavior-free with respect to the objective.

# InMemoryGoalRepository

V1 provides:

```text
InMemoryGoalRepository
```

for deterministic in-process persistence.

It stores goals by UUID and returns all goals in insertion order.

```text
save Goal A
save Goal B
save Goal C

       │
       ▼

goals()

Goal A
Goal B
Goal C
```

# SQLiteGoalRepository

V1 also provides:

```text
SQLiteGoalRepository
```

for durable persistence across process restart.

A stored goal round-trips through serialization back into the canonical `Goal`
domain model.

Conceptually:

```text
Goal
 │
 ▼
SQLite
 │
 ▼
process restart
 │
 ▼
Goal
```

The reconstructed object is a new Python object representing the same durable
domain value.

# Duplicate Goal Identity Is Rejected

Both current repository implementations treat goal identity as durable.

Persisting another goal with the same UUID is rejected.

```text
save Goal(id=A)

save Goal(id=A)

        ✗
```

The repository does not silently replace the existing objective.

This prevents objective semantics from changing invisibly under an identity
already referenced by empirical artifacts.

# Goal Persistence Is Append-Oriented

At the V1 repository boundary:

```text
existing goal identity
       │
       ▼
cannot be overwritten by save()
```

This gives persisted goal artifacts append-oriented identity semantics.

If objective semantics change, that change should be explicit rather than
hidden behind an overwrite.

# GoalCatalog

`GoalCatalog` is an immutable ordered inventory of configured goals.

Conceptually:

```text
GoalCatalog
├── Goal A
├── Goal B
└── Goal C
```

The catalog exposes:

```text
goals

identifiers

get(goal_id)
```

# Goal Catalog Order

`GoalCatalog` preserves the order supplied to it.

When reconstructed through a repository loader, repository insertion order
becomes catalog order.

```text
repository order
      │
      ▼
catalog order
```

No implicit sorting or ranking occurs.

# Goal Lookup

A goal can be resolved by exact UUID:

```text
goal_id
   │
   ▼
GoalCatalog.get()
```

Unknown identities return:

```text
None
```

The catalog does not infer another goal.

# GoalCatalog Is Immutable

The catalog itself is frozen.

The configured inventory therefore behaves as a runtime snapshot rather than a
mutable shared registry.

To observe different durable repository contents, an application reconstructs
the appropriate catalog.

# GoalCatalogLoader

`GoalCatalogLoader` reconstructs an immutable `GoalCatalog` from a
`GoalRepository`.

```text
GoalRepository
      │
      ▼
GoalCatalogLoader
      │
      ▼
GoalCatalog
```

Its implementation deliberately performs no additional policy.

Conceptually:

```python
GoalCatalog(
    goals=repository.goals(),
)
```

Repository order is retained.

# Catalog Loading Is Not Goal Selection

Loading goals answers:

```text
Which durable goals are configured?
```

It does not answer:

```text
Which goal should this workflow pursue?
```

That choice belongs to the application or higher-level empirical operation
constructing the relevant artifact.

# Goal Persistence Stores Semantics, Not Behavior

The persisted state contains:

```text
id

name

description

success criteria

constraints
```

It does not contain:

```text
Strategy

WorkflowCandidate

Evaluator

ExecutionResult

optimization generation

production state
```

This preserves the goal as pure durable intent.

# Goals and OptimizationExample

One important V1 integration is `OptimizationExample`.

An optimization example can carry a complete immutable `Goal` together with a
reproducible scenario.

Conceptually:

```text
Goal
  +
Context
  +
ExpectedOutcome
      │
      ▼
OptimizationExample
```

The goal states the broader objective.

The context defines the scenario.

The expected outcome defines what that particular example should produce.

# One Goal, Many Examples

A single goal may be reused across many optimization examples.

```text
                     Goal
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
    Example A     Example B     Example C
```

Each example can have different:

```text
Context

ExpectedOutcome
```

while still testing behavior against the same larger objective.

This supports empirical generalization rather than optimizing for only one
example.

# Goal Snapshot Semantics

When an optimization example embeds a `Goal`, it contains the complete
immutable goal value.

Conceptually:

```text
GoalRepository
      │
      ▼
GoalCatalogLoader
      │
      ▼
Goal
      │
      ▼
OptimizationExample
      │
      └── embedded Goal value
```

The example does not dynamically query the goal repository every time the goal
is needed.

That distinction matters.

# Repository State Is Not Example State

Suppose:

```text
Goal A
```

is loaded and embedded into an empirical example.

Persisting other goals later does not alter that existing example.

```text
OptimizationExample
      │
      ▼
embedded immutable Goal A
```

remains the objective snapshot under which that example was defined.

The example's meaning does not depend on a live mutable repository view.

# Goals and Expected Outcomes

Goals and expected outcomes are complementary.

```text
Goal
    broad intent

ExpectedOutcome
    concrete expectation
```

For example:

```text
Goal:
    Classify support requests accurately.

Example 1 ExpectedOutcome:
    duplicate_charge

Example 2 ExpectedOutcome:
    account_access

Example 3 ExpectedOutcome:
    refund_request
```

This lets one stable objective govern many reproducible cases.

# Goals and Evaluation

The goal package does not evaluate output.

Evaluation requires:

```text
ExpectedOutcome

actual value

Evaluator
```

not merely a `Goal`.

Conceptually:

```text
Goal
   │
   ▼
helps define empirical intent

ExpectedOutcome + actual
   │
   ▼
Evaluator
   │
   ▼
EvaluationResult
```

The goal remains outside executable judgment.

# Goals and Strategies

Strategies may attempt to satisfy a goal.

```text
Goal
 │
 ├── Strategy A
 ├── Strategy B
 └── Strategy C
```

The goal does not contain those strategies.

The strategies do not redefine the goal.

This allows executable behavior to evolve while objective identity remains
stable.

# Goals and Prompting

A prompt can change while the goal remains constant.

```text
Goal
 │
 ├── Prompt A
 ├── Prompt B
 └── Prompt C
```

Prompt experimentation therefore does not require modifying objective
semantics.

# Goals and Models

Likewise:

```text
Goal
 │
 ├── provider/model A
 ├── provider/model B
 └── provider/model C
```

may all represent different attempts to satisfy the same objective.

Model selection belongs to prompting, workflows, runtime composition, and
optimization—not the goal model.

# Goals and Tools

A workflow may introduce, remove, or replace tool-backed behavior while
retaining the same goal.

```text
Goal
 │
 ├── workflow without tool
 ├── workflow with tool A
 └── workflow with tool B
```

The goal does not authorize or resolve tools.

# Goals and Workflows

A workflow provides executable orchestration.

A goal provides objective semantics.

```text
Goal
    what should be achieved

WorkflowSpecification
    durable orchestration intent

WorkflowCandidate
    executable realization
```

These layers should not be collapsed.

# Goals and Experiments

Experiments compare empirical behavior.

Goals provide stable objective context for that empirical work.

```text
Goal
   │
   ▼
reproducible examples
   │
   ▼
candidate executions
   │
   ▼
evaluation evidence
   │
   ▼
experiment
```

The experiment can compare different implementation choices while retaining a
shared objective.

# Goals and Optimization

Optimization can change the means used to pursue a goal.

```text
Goal
  │
  ▼
candidate A
candidate B
candidate C
  │
  ▼
empirical evidence
  │
  ▼
optimizer
  │
  ▼
new candidate population
```

The optimizer does not mutate the goal.

The goal provides stable intent while candidate behavior evolves.

# Goals and Production

The complete separation is:

```text
Goal
    what we want

WorkflowSpecification
    durable behavioral design

WorkflowCandidate
    executable realization

EvaluationResult
    empirical judgment

WorkflowProductionState
    what production is currently intended to execute
```

No one of these artifacts substitutes for another.

# Goals Are Not Policies

Because success criteria and constraints are descriptive strings, a goal should
not be mistaken for an executable policy engine.

For example:

```text
constraint:
    "Remain provider independent."
```

does not automatically alter:

```text
ModelPortfolio

ModelCatalog

FixedModelSelection

WorkflowProductionState
```

If such a requirement must become operational, the responsible subsystem must
model and enforce it explicitly.

# Goals Are Not Evaluation Specifications

A goal may say:

```text
"The answer remains factual."
```

but that does not specify:

```text
which evaluator measures factuality

what score threshold passes

what evidence is required
```

Those concerns belong to evaluation and higher-level experiment design.

# Goals Are Not Optimization Instructions

A constraint such as:

```text
"Stay within an acceptable cost budget."
```

does not itself instruct an optimizer to:

```text
choose the cheapest model

apply a particular pricing threshold

stop after a given generation
```

Optimizer policy remains explicit and separate.

# Goals Are Not Runtime Configuration

`Goal` does not belong to `AzathothRuntime` merely because it is durable.

The runtime composition boundary concerns configured executable workflow
dependencies.

Goals are reusable objective artifacts that can be selected when constructing
the empirical work that needs them.

# Complete V1 Goal Architecture

```text
                          DURABLE INTENT

                              Goal
                    ┌──────────┼──────────┐
                    │          │          │
                    ▼          ▼          ▼
                  name    success       constraints
                         criteria
                    │          │          │
                    └──────────┼──────────┘
                               │
                               ▼

                         GoalRepository
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          InMemoryGoalRepository   SQLiteGoalRepository
                    │                     │
                    └──────────┬──────────┘
                               ▼
                       GoalCatalogLoader
                               │
                               ▼
                          GoalCatalog
                               │
                               ▼
                              Goal
                               │
                               ▼

                     EMPIRICAL COMPOSITION

                      OptimizationExample
                     ┌────────┼────────┐
                     ▼        ▼        ▼
                   Goal    Context  ExpectedOutcome
                     │
                     ▼
              candidate execution
                     │
                     ▼
                  evaluation
                     │
                     ▼
                  experiment
                     │
                     ▼
                 optimization
```

The goal remains stable throughout the empirical lifecycle.

# V1 Goal Principles

The V1 goal architecture can be summarized as:

```text
objective
    ≠
implementation

success criterion
    ≠
evaluator

constraint
    ≠
runtime policy

goal
    ≠
expected outcome

goal
    ≠
strategy

goal
    ≠
workflow

goal
    ≠
optimizer

goal
    ≠
production authority

repository state
    ≠
live objective mutation
```

The central rule is:

```text
Describe what success means.

Keep that intent durable.

Let every other subsystem prove how well it can satisfy it.
```

That gives Azathoth a stable objective boundary while strategies, workflows,
models, evaluators, and optimization algorithms remain free to evolve
empirically.