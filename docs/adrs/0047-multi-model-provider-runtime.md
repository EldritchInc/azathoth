# ADR 0047: Assemble Multi-Model Provider Runtimes

- Status: Accepted
- Date: 2026-08-20

## Context

Azathoth separates model requirements, model metadata, and executable language
model implementations.

A model-backed workload declares what kind of model it requires using
`ModelRequirements`.

```text
ModelRequirements
        │
        ▼
    ModelQuery
        │
        ▼
   ModelCatalog
        │
        ▼
 eligible models
```

The workload does not need to name a concrete provider model.

`ModelCatalog` describes configured model identities and capabilities.

`LanguageModelRegistry` resolves provider-qualified model identifiers to
executable `LanguageModel` implementations.

```text
ModelCatalog
    │
    │ describes
    ▼
ModelMetadata

LanguageModelRegistry
    │
    │ resolves
    ▼
LanguageModel
```

OpenRouter exposes many models through one provider API and one provider
configuration.

Treating one OpenRouter credential set as if it represented one globally
selected model would prevent independent workflow steps from resolving models
according to their own requirements.

## Decision

One OpenRouter configuration may produce executable runtime registrations for
multiple configured OpenRouter models.

```text
OpenRouterConfiguration
          +
     ModelCatalog
          │
          ▼
OpenRouterModelRegistryLoader
          │
          ▼
LanguageModelRegistry
├── openrouter/model-a
├── openrouter/model-b
├── openrouter/model-c
└── openrouter/model-d
```

`OpenRouterModelRegistryLoader` considers only OpenRouter model metadata from the
supplied catalog.

For each configured OpenRouter model, it creates an independently executable
`OpenRouterLanguageModel`.

The loader does not select a winning model.

It only makes configured OpenRouter models executable.

## Provider Configuration Is Not Model Selection

`OpenRouterConfiguration` describes access to the provider.

It does not identify the model a workload must use.

```text
OpenRouterConfiguration
├── api key
├── base URL
└── timeout

            ≠

specific workload model
```

Concrete model identity remains part of model metadata and runtime binding.

This allows one provider configuration to support many model-backed workflow
steps simultaneously.

## Registry Composition

Executable model registries may be composed.

```text
LanguageModelRegistry A
├── provider-a/model-1
└── provider-a/model-2

LanguageModelRegistry B
├── provider-b/model-3
└── provider-b/model-4

            │
            ▼
LanguageModelRegistry.compose(...)
            │
            ▼
Combined Registry
├── provider-a/model-1
├── provider-a/model-2
├── provider-b/model-3
└── provider-b/model-4
```

Composition preserves registry order and model order.

Duplicate provider-qualified model identifiers are rejected.

Composition does not mutate its source registries.

No registry is treated as a privileged base registry.

## Model Discovery Remains Separate From Execution

Runtime assembly does not change the model-discovery boundary.

```text
ModelRequirements
        │
        ▼
    ModelCatalog
        │
        ▼
eligible metadata
        │
        │ intersect with
        ▼
LanguageModelRegistry
        │
        ▼
executable candidates
```

A model may exist in the catalog without having an executable runtime
implementation.

A runtime implementation may exist without satisfying a workload's
requirements.

A prompt candidate is produced only when both conditions hold.

## Per-Step Model Resolution

Each prompt-backed workflow step has its own `PromptStrategySpec`.

Each prompt specification has its own `ModelRequirements`.

Workflow candidate generation therefore resolves models independently for each
prompt-backed step.

```text
WorkflowSpecification
│
├── Step A
│   └── ModelRequirements A
│           │
│           ▼
│        Model A
│
├── Step B
│   └── ModelRequirements B
│           │
│           ▼
│        Model C
│
└── Step C
    └── ModelRequirements C
            │
            ▼
         Model B
```

A workflow does not have one global language model.

Different steps in one workflow may execute different concrete models from the
same provider or from different providers.

## Deterministic Candidate Resolution

Configured catalog order remains deterministic.

Candidate generation evaluates eligible models in catalog order and retains
only models with executable registry implementations.

The provider runtime does not introduce model ranking or optimization policy.

A workflow step may use requirements that leave exactly one model eligible.

For example:

```text
Model A
├── inexpensive
└── no structured-output capability

Model B
├── higher price
└── structured-output capable


Step A
requires low price
      │
      ▼
   Model A


Step B
requires structured output
      │
      ▼
   Model B
```

The resulting model bindings are determined from the declared requirements and
configured model metadata.

## Runtime Model Binding

Candidate generation attaches a concrete `ModelBinding` to each generated
prompt strategy.

```text
PromptStrategySpec
        │
        ▼
candidate generation
        │
        ▼
PromptStrategy
        │
        ▼
ModelBinding
        │
        ▼
provider/model
```

This preserves the distinction between model-independent specification and
concrete execution.

The workflow specification remains portable configuration.

The candidate records the concrete runtime choice.

## Execution Evidence

Each model-backed step records provider-neutral execution metrics.

These include:

- provider;
- model;
- prompt tokens;
- completion tokens;
- total tokens;
- latency; and
- estimated cost.

A heterogeneous workflow therefore preserves evidence separately for each
model-backed step.

```text
WorkflowRun
│
├── Step A
│   ├── provider = openrouter
│   ├── model = model-a
│   ├── tokens
│   ├── latency
│   └── cost
│
└── Step B
    ├── provider = openrouter
    ├── model = model-b
    ├── tokens
    ├── latency
    └── cost
```

Higher-level systems can inspect this evidence without depending on
OpenRouter-specific runtime objects.

## Requested and Resolved OpenRouter Identity

OpenRouter may resolve an alias or routed model identifier to a concrete served
model.

Azathoth therefore preserves both:

```text
ModelResponse.model
    configured/requested model

ModelResponse.resolved_model
    model reported by OpenRouter
```

The configured model remains the binding identity used by Azathoth.

The resolved model records what OpenRouter reported for the actual request.

This allows routed or aliased OpenRouter models to retain both configuration and
execution identity.

## Live Verification

Normal test execution remains deterministic and does not consume provider
credits.

Live OpenRouter verification remains explicit opt-in behavior.

Multi-model live verification accepts a set of test model identifiers and
constructs one registry containing all of them.

```text
OPENROUTER_TEST_MODELS
        │
        ▼
   test ModelCatalog
        │
        ▼
OpenRouterModelRegistryLoader
        │
        ▼
 multi-model registry
        │
        ▼
 real OpenRouter API
```

The test environment variable selects models for optional live verification.

It is not a production model-selection mechanism.

Production model eligibility remains determined by model metadata,
`ModelRequirements`, catalog discovery, and runtime registration.

## Consequences

### Positive

- One OpenRouter configuration can execute many models.
- Different workflow steps can independently resolve different models.
- Provider credentials are separated from model selection.
- OpenRouter can coexist with other executable providers.
- Registry composition is deterministic.
- Duplicate runtime identities are rejected.
- Workflow specifications remain provider-neutral.
- Concrete model bindings remain explicit.
- Per-step usage, cost, and model evidence remain observable.
- OpenRouter aliases can retain both requested and resolved model identity.

### Negative

- Applications must assemble both model metadata and runtime registrations.
- Model metadata must accurately describe capabilities and pricing for
  requirement-based discovery to be meaningful.
- Runtime assembly does not automatically discover OpenRouter model metadata.
- The first eligible candidate remains determined by configured catalog order
  unless a higher-level system performs empirical comparison.

## Alternatives Considered

### Configure One Global OpenRouter Model

Rejected.

A workflow may contain steps with different capability, context-window, or cost
requirements.

One global model would collapse workload specification into application
configuration and prevent heterogeneous execution.

### Store Concrete OpenRouter Model Names in Workflow Steps

Rejected as the normal model-selection mechanism.

Prompt-backed workflow specifications declare provider-neutral model
requirements.

Concrete model identity belongs to runtime candidate generation and binding.

### Mutate One Shared Registry

Rejected.

Runtime composition should be explicit and deterministic.

Registry composition returns a new registry and leaves source registries
unchanged.

### Allow Duplicate Registry Identifiers With Last-Write-Wins Behavior

Rejected.

Silently replacing an executable model implementation would make runtime
identity depend on composition order in an implicit way.

Duplicate provider-qualified identifiers are configuration errors.

### Put Model Ranking in the OpenRouter Loader

Rejected.

The loader assembles executable runtime implementations.

It does not evaluate, score, rank, or optimize models.

## Result

Azathoth supports heterogeneous multi-model execution without introducing a
global provider-model setting.

```text
                  ModelCatalog
                      +
              Runtime Registries
                      │
                      ▼
              Candidate Generation
             /         |         \
            ▼          ▼          ▼
         Step A      Step B      Step C
           │           │           │
           ▼           ▼           ▼
        Model A      Model C      Model B
             \         |         /
                      ▼
                 WorkflowRun
                      │
             per-step model evidence
```

Provider configuration supplies access.

Model requirements describe workload needs.

Catalogs describe available models.

Registries make models executable.

Candidate generation binds concrete models independently for each step.

Multi-model provider runtime introduces no model-ranking or optimization policy.