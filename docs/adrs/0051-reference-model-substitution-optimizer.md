# ADR 0051: Provide Reference Model Substitution Optimization

- Status: Accepted
- Date: 2026-08-22

## Context

Azathoth separates empirical workflow experiments from optimization policy.

```text
candidate population
        │
        ▼
experiment
        │
        ▼
execution evidence
        │
        ▼
evaluation
        │
        ▼
scorecards
        │
        ▼
ranking
        │
        ▼
optimizer
        │
        ▼
next candidate population
```

`WorkflowOptimizer` defines the boundary between evidence from one generation
and the candidate population proposed for the next.

Before this decision, `ReplayWorkflowOptimizer` provided a reference
implementation of that protocol by returning the current population unchanged.

That proved:

- experiment evidence could reach an optimizer;
- optimizer output could become the next population; and
- optimization sessions could execute repeatedly across generations.

It deliberately did not improve workflow candidates.

Azathoth therefore had a complete empirical optimization loop without a
built-in implementation demonstrating a concrete workflow modification.

## Decision

Azathoth provides a reference model-substitution optimizer.

```text
ModelSubstitutionWorkflowOptimizer
```

The reference optimizer mechanically explores strictly cheaper eligible
language-model bindings.

It does not determine whether a substitution is better.

```text
current candidate
      │
      ▼
inspect prompt-backed steps
      │
      ▼
find eligible configured models
      │
      ▼
retain executable models
      │
      ▼
retain strictly cheaper models
      │
      ▼
generate candidate substitutions
```

The resulting candidates must execute through the normal experiment,
evaluation, scoring, and ranking pipeline before any substitution can be
considered an empirical improvement.

## Mechanical Search Policy

For each prompt-backed workflow step, model substitution begins with the
step's declared `ModelRequirements`.

```text
PromptStrategySpec
        │
        ▼
ModelRequirements
        │
        ▼
ModelQuery
        │
        ▼
ModelCatalog
```

Only models satisfying those declared requirements are eligible.

The target model must also have an executable implementation in the
`LanguageModelRegistry`.

```text
eligible metadata
       +
runtime implementation
       │
       ▼
candidate substitution
```

The reference optimizer introduces no inference about whether a model is
likely to succeed.

Eligibility means only that the model satisfies declared requirements and can
execute.

## Strictly Cheaper Models

A target model is considered strictly cheaper only when its configured pricing
Pareto-dominates the current model pricing.

```text
target input price  <= current input price
target output price <= current output price
```

and at least one dimension must be strictly lower.

```text
target input price  < current input price

OR

target output price < current output price
```

This intentionally avoids estimating workload-specific token ratios or
introducing optimization heuristics into the reference implementation.

Models without comparable configured pricing are not proposed as cheaper
substitutions.

A model that lowers one price dimension while increasing the other is not
considered strictly cheaper by this optimizer.

## Candidate Regeneration

Model substitution does not mutate an executable `PromptStrategy` in place.

Instead, the substituted prompt step is regenerated through the normal prompt
candidate-generation path.

```text
PromptStrategySpec
        +
target ModelMetadata
        +
LanguageModelRegistry
        │
        ▼
generate_prompt_candidates()
        │
        ▼
PromptStrategy
```

This preserves the existing deterministic strategy-identity rules associated
with the specification and selected model.

The regenerated strategy then replaces only the corresponding step in the
workflow candidate.

```text
WorkflowCandidate
├── Step A
├── Step B  ──────┐
└── Step C        │
                  ▼
           regenerated Step B
                  │
                  ▼
WorkflowCandidate'
├── Step A
├── Step B'
└── Step C
```

Each generated candidate therefore represents a one-step model substitution.

## Population Expansion

`ModelSubstitutionWorkflowOptimizer` preserves the current candidate population
as empirical baselines.

It then adds cheaper legal substitutions.

```text
Candidate A
├── preserve Candidate A
├── substitution A.1
└── substitution A.2

Candidate B
├── preserve Candidate B
└── substitution B.1
```

Preserving the baseline is required because cheaper pricing alone does not
establish that a candidate is better.

The next experiment must remain capable of preferring the original candidate
when substitutions reduce quality, reliability, or other measured dimensions.

## Candidate Deduplication

Different parent candidates may produce the same executable workflow
configuration.

The reference optimizer deduplicates equivalent proposals before returning the
next population.

Candidate identity is derived from the ordered strategy identities of its
steps.

```text
WorkflowCandidate
        │
        ▼
ordered step strategy IDs
        │
        ▼
candidate signature
```

Prompt strategy identities already incorporate the selected model binding.

Equivalent resolved configurations therefore share the same signature.

This avoids executing duplicate model calls during the next experiment.

## Evidence Remains Authoritative

The optimizer does not declare a proposed candidate successful.

```text
optimizer
   │
   │ proposes
   ▼
candidate
   │
   ▼
experiment
   │
   ├── execute
   ├── evaluate
   ├── score
   └── rank
```

A cheaper candidate may fail.

It may produce worse output.

It may be less reliable.

It may have undesirable latency.

The optimizer does not override any of those observations.

A proposal becomes an empirical improvement only when the normal workflow
experiment machinery measures and ranks it accordingly.

## Empirical Cost Improvement

The reference optimizer is tested through a complete multi-generation
optimization session.

```text
Generation 0

expensive model
      │
      ▼
execute
      │
      ▼
quality passes
cost measured


        ↓ optimizer


Generation 1 population

expensive baseline
cheaper model
cheapest model
      │
      ▼
execute all candidates
      │
      ▼
evaluate all candidates
      │
      ▼
score all candidates
      │
      ▼
rank all candidates
```

When every model produces the same correct result but execution evidence
reports lower cost for the cheaper substitutions, the normal workflow scorer
assigns the cheaper execution a better cost score.

The normal workflow ranking then places the empirically stronger scorecard
ahead of the baseline.

The optimizer itself does not manufacture this result.

## Relationship to Model Metadata and Execution Evidence

Configured pricing determines which substitutions the optimizer may propose.

```text
ModelMetadata.pricing
        │
        ▼
proposal eligibility
```

Actual execution evidence determines how a candidate performed.

```text
ModelResponse
        │
        ▼
StrategyExecutionMetrics
        │
        ▼
WorkflowRun
        │
        ▼
WorkflowScorer
```

These are deliberately different responsibilities.

Configured model pricing defines the mechanical search space.

Observed execution metrics provide empirical evidence.

## Relationship to ReplayWorkflowOptimizer

`ReplayWorkflowOptimizer` remains useful as the minimal reference implementation
of the optimization protocol.

```text
ReplayWorkflowOptimizer

population N
    │
    ▼
same population
```

`ModelSubstitutionWorkflowOptimizer` demonstrates actual candidate variation.

```text
ModelSubstitutionWorkflowOptimizer

population N
    │
    ▼
baseline + cheaper substitutions
```

Together they demonstrate two distinct properties:

- optimization sessions can iterate independently of adaptive policy; and
- an optimizer can produce new candidates that are empirically evaluated in
  later generations.

## Deliberately Limited Intelligence

The reference model-substitution optimizer is intentionally mechanical.

It does not perform:

- failure clustering;
- semantic failure analysis;
- context partition discovery;
- routing synthesis;
- tool insertion;
- prompt mutation;
- workflow topology mutation;
- learned search;
- exploration-versus-exploitation planning;
- model-quality prediction;
- experiment planning; or
- LLM-guided optimization.

It answers only:

> Which strictly cheaper, requirements-compatible, executable model bindings
> could be tried next?

The empirical workflow machinery answers whether any of those proposals are
actually better.

## Current Experiment Association Limitation

`WorkflowExperimentResult` currently records scorecards and their ranking
without embedding an explicit scorecard-to-candidate association.

The reference optimizer therefore does not attempt to infer which current
candidate produced the winning scorecard.

It mechanically expands the supplied current population.

This avoids relying on implicit tuple-position relationships between candidate
populations and experiment artifacts.

Future evidence-directed optimizers should use an explicit durable association
between candidates and their empirical evidence before making decisions based
on candidate-specific historical performance.

## Consequences

### Positive

- OSS Azathoth contains a real optimizer implementation.
- Optimization sessions can produce genuinely different workflow candidates.
- Model requirements remain authoritative during substitution.
- Runtime executability remains required.
- Existing candidate-generation identity semantics are preserved.
- Baselines remain available for empirical comparison.
- Duplicate executable configurations are removed.
- Improvement claims remain grounded in execution evidence.
- The reference optimizer demonstrates measurable cost improvement without
  introducing sophisticated optimization policy.
- The optimizer remains provider-neutral.

### Negative

- The optimizer explores only one-step model substitutions.
- It requires comparable configured model pricing.
- Pareto price dominance deliberately excludes some potentially useful model
  tradeoffs.
- It expands the entire supplied population rather than selecting candidates
  from experiment evidence.
- It does not reason about historical failures.
- Population size may grow with the number of eligible models and model-backed
  steps.

## Alternatives Considered

### Ship Only ReplayWorkflowOptimizer

Rejected for OSS V1.

Replay proves iterative orchestration but cannot demonstrate that an optimizer
can produce a concrete workflow improvement.

### Select the Previous Experiment Winner by Tuple Position

Rejected.

`WorkflowExperimentResult` does not currently encode an explicit
candidate-to-scorecard association.

Optimization policy should not depend on an undocumented positional
relationship.

### Mutate PromptStrategy Model Bindings Directly

Rejected.

Prompt strategies are resolved executable candidates with deterministic
identity semantics.

Substituted strategies should be regenerated through the normal candidate
generation boundary.

### Treat Any Lower Aggregate Price as Cheaper

Rejected.

Doing so would require assumptions about workload-specific input/output token
ratios.

The reference implementation uses the simpler and deterministic Pareto
criterion.

### Remove the Original Candidate After Finding Cheaper Models

Rejected.

Cheaper configured pricing does not prove equal quality or reliability.

The original candidate remains an empirical baseline until experiments
demonstrate that another candidate is stronger.

### Add Sophisticated Adaptive Search to the Reference Optimizer

Rejected.

The OSS reference optimizer exists to demonstrate the optimization extension
point and empirical improvement lifecycle.

Advanced optimization policy is outside this decision.

## Result

Azathoth now includes a reference optimizer capable of producing real workflow
changes.

```text
current workflow
      │
      ▼
mechanical cheaper-model proposals
      │
      ▼
next experiment
      │
      ▼
real execution evidence
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
empirically measured improvement
```

The optimizer proposes.

The experiment measures.

The evidence decides.