# Prompting

`azathoth.prompting` defines Azathoth's prompt-backed strategy architecture.

The package separates durable prompt intent from runtime model binding and
execution.

```text
PromptStrategySpec
        │
        ▼
model-selection authority
        │
        ▼
candidate generation
        │
        ▼
PromptStrategy
        │
        ▼
LanguageModel
```

This separation allows workflows to describe prompt-backed behavior without
persisting live provider implementations inside workflow configuration.

## Architectural Role

Prompting sits between durable workflow intent and provider-backed execution.

```text
durable intent
     │
     ▼
PromptStrategySpec
     │
     ▼
ModelSelection
     │
     ├── PortfolioModelSelection
     │
     └── FixedModelSelection
     │
     ▼
ModelCatalog
ModelPortfolio
LanguageModelRegistry
     │
     ▼
generate_prompt_candidates()
     │
     ▼
PromptStrategy
     │
     ▼
LanguageModel.complete()
```

The package owns:

- prompt-backed strategy specifications;
- model-selection intent;
- prompt candidate generation;
- runtime model binding;
- context-backed prompt rendering;
- prompt execution; and
- translation of model responses into strategy outcomes.

It does not own:

- provider discovery;
- organizational model authorization;
- workflow orchestration;
- evaluation;
- scoring;
- ranking;
- optimization policy; or
- production promotion.

## Public Surface

The V1 prompting package exports:

```python
from azathoth.prompting import (
    ContextPromptStrategy,
    FixedModelSelection,
    ModelBinding,
    ModelBindingMismatchError,
    ModelSelection,
    PortfolioModelSelection,
    PromptBinding,
    PromptBindingError,
    PromptBindingEventNotFoundError,
    PromptBindingFieldNotFoundError,
    PromptStrategy,
    PromptStrategySpec,
    PromptTemplate,
    PromptingError,
    generate_prompt_candidates,
)
```

These objects cover three related but distinct concerns:

```text
specification

candidate generation

execution
```

Keeping those concerns separate is central to the V1 architecture.

# PromptStrategySpec

`PromptStrategySpec` describes a prompt-backed strategy without binding it to
an executable language-model implementation.

Conceptually:

```text
PromptStrategySpec
├── metadata
├── prompt
└── model_selection
```

It is immutable.

The specification answers:

```text
What prompt behavior is intended?

What authority governs model selection?
```

It does not answer:

```text
Which live LanguageModel Python object should execute right now?
```

That decision belongs to runtime candidate generation.

## Durable Intent Versus Executable Realization

The core distinction is:

```text
PromptStrategySpec
    durable/model-independent intent

PromptStrategy
    executable runtime realization
```

A workflow can therefore persist:

```text
prompt
+
model-selection intent
```

without persisting:

```text
network clients
provider SDK objects
credentials
live executable model implementations
```

This keeps durable configuration separate from process-local execution
capabilities.

# Model Selection Authority

Every prompt specification carries an explicit `ModelSelection`.

V1 provides two forms:

```text
ModelSelection
├── PortfolioModelSelection
└── FixedModelSelection
```

These represent materially different authority models.

# PortfolioModelSelection

`PortfolioModelSelection` allows Azathoth to choose among currently available,
organizationally authorized models satisfying declared requirements.

```text
PortfolioModelSelection
        │
        ▼
ModelRequirements
```

The object is immutable.

Example:

```python
from azathoth.prompting import PortfolioModelSelection
from azathoth.providers import ModelRequirements

selection = PortfolioModelSelection(
    requirements=ModelRequirements(),
)
```

The selection does not name an exact model.

Instead it states:

```text
Azathoth may choose among models that:

1. are organizationally authorized;
2. are present in the current model catalog;
3. satisfy these requirements; and
4. have executable runtime implementations.
```

This makes portfolio selection suitable for experimentation and optimization,
where multiple legitimate executable candidates may be compared.

# FixedModelSelection

`FixedModelSelection` requires one exact provider-qualified model.

```text
FixedModelSelection
├── provider
└── model
```

Example:

```python
from azathoth.prompting import FixedModelSelection

selection = FixedModelSelection(
    provider="example-provider",
    model="example-model",
)
```

Its derived identifier is:

```text
example-provider/example-model
```

The provider-qualified identifier is derived from `provider` and `model`; it is
not persisted as a third independent field.

Conceptually:

```text
provider + model
      │
      ▼
provider/model
```

This prevents the persisted identifier from drifting out of agreement with the
two authoritative fields.

## Fixed Selection Semantics

Fixed selection means:

```text
use this exact provider/model
```

It does not mean:

```text
choose something equivalent
choose another authorized model
fall back through the portfolio
pick the cheapest compatible model
```

During ordinary prompt candidate generation, Azathoth looks up the exact model
in the current `ModelCatalog`.

If that model is absent, no candidate is produced.

If the catalog model exists but no executable implementation exists in the
`LanguageModelRegistry`, no candidate is produced.

The selection remains exact.

# Portfolio Authorization Versus Fixed Authority

The distinction between the two selection types is deliberate.

For portfolio selection:

```text
ModelCatalog
     +
ModelPortfolio
     │
     ▼
authorized current catalog
     │
     ▼
ModelRequirements
     │
     ▼
eligible models
```

For fixed selection:

```text
FixedModelSelection
        │
        ▼
exact provider/model
        │
        ▼
ModelCatalog.get()
```

A fixed selection does not silently become portfolio selection.

That distinction is important throughout Azathoth's workflow and production
architecture.

# Candidate Generation

`generate_prompt_candidates()` turns one `PromptStrategySpec` into zero or more
executable `PromptStrategy` objects.

Its inputs are:

```text
PromptStrategySpec

ModelCatalog

ModelPortfolio

LanguageModelRegistry
```

Conceptually:

```text
PromptStrategySpec
        │
        ▼
inspect ModelSelection
        │
        ├──────────────────────────┐
        │                          │
        ▼                          ▼
PortfolioModelSelection      FixedModelSelection
        │                          │
        ▼                          ▼
ModelPortfolio ∩ Catalog      exact Catalog lookup
        │                          │
        ▼                          │
requirements query                │
        │                          │
        └────────────┬─────────────┘
                     ▼
              eligible metadata
                     │
                     ▼
           LanguageModelRegistry
                     │
                     ▼
              executable models
                     │
                     ▼
              PromptStrategy
```

Candidate generation does not call the provider.

It composes metadata and executable implementations into strategies that can
later be executed.

# Portfolio Candidate Generation

For `PortfolioModelSelection`, candidate generation first constructs a catalog
restricted to the `ModelPortfolio`.

```text
current ModelCatalog
        │
        +
ModelPortfolio
        │
        ▼
model_catalog_for_portfolio()
        │
        ▼
authorized current models
```

It then translates the declared `ModelRequirements` into a `ModelQuery`.

```text
ModelRequirements
       │
       ▼
ModelQuery
       │
       ▼
catalog.find()
```

Only models satisfying the requirements remain eligible.

Candidate generation then checks the executable registry.

```text
eligible ModelMetadata
        │
        ▼
LanguageModelRegistry.get(identifier)
        │
        ├── implementation exists ──► candidate
        │
        └── implementation absent ──► skip
```

The resulting candidate set therefore represents the intersection of:

```text
organizational authorization

current provider-derived metadata

declared model requirements

runtime executability
```

These are intentionally separate concepts.

# Fixed Candidate Generation

For `FixedModelSelection`, Azathoth resolves the exact provider-qualified model.

```text
FixedModelSelection.identifier
        │
        ▼
ModelCatalog.get()
```

If the metadata exists, candidate generation attempts to resolve the matching
`LanguageModel` implementation from the registry.

```text
catalog metadata
      +
registry implementation
      │
      ▼
PromptStrategy
```

No alternate model is inferred.

# Deterministic Candidate Identity

Generated prompt candidates receive deterministic strategy identifiers.

The identifier is derived using:

```text
original specification strategy ID
        +
provider-qualified model identifier
```

Conceptually:

```text
uuid5(
    specification.metadata.id,
    model.identifier,
)
```

Therefore:

```text
same specification identity
        +
same model identity
        =
same generated strategy identity
```

This gives candidate generation reproducible identity across executions and
experiments.

Different model bindings produce different strategy identities.

# Generated Strategy Metadata

Candidate generation preserves the specification's:

```text
description
version
```

while producing model-specific runtime strategy identity and name.

Conceptually:

```text
Specification Strategy
    "Classify request"

        │ bind provider/model
        ▼

Generated Strategy
    "Classify request [provider/model]"
```

The executable candidate remains traceable back to the durable specification
while distinguishing different model realizations.

# ModelBinding

Every generated prompt candidate receives a `ModelBinding`.

```text
PromptStrategy
     │
     └── ModelBinding
             │
             ▼
       provider/model
```

`ModelBinding` is immutable and records the provider-qualified model the
strategy is expected to execute against.

Example:

```python
from azathoth.prompting import ModelBinding

binding = ModelBinding(
    identifier="example-provider/example-model",
)
```

The binding is more than informational metadata.

It validates execution evidence.

# Binding Validation

After model execution, the provider's `ModelResponse` reports:

```text
provider
model
```

Azathoth derives:

```text
provider/model
```

and compares it with the configured binding.

```text
ModelBinding
example-provider/example-model
          │
          ▼
      compare
          ▲
          │
ModelResponse
provider + model
```

If they differ, execution raises `ModelBindingMismatchError`.

This establishes an important evidence invariant:

```text
recorded model identity
        =
model Azathoth intended to execute
```

Provider responses cannot silently be attributed to the wrong candidate.

# Model Requirements on Generated Strategies

When a candidate originates from `PortfolioModelSelection`, its
`PromptStrategy` retains the relevant `ModelRequirements`.

```text
PortfolioModelSelection
        │
        ▼
ModelRequirements
        │
        ▼
generated PromptStrategy
```

When a candidate originates from `FixedModelSelection`, the generated strategy
does not need requirements to justify its model identity.

The exact model selection itself supplied the authority.

This preserves the distinction between:

```text
selected because it satisfied requirements

and

selected because this exact model was required
```

# PromptStrategy

`PromptStrategy` is an executable language-model-backed strategy.

It combines:

```text
StrategyMetadata
Prompt
LanguageModel
optional ModelRequirements
optional ModelBinding
```

Unlike `PromptStrategySpec`, it contains a live executable `LanguageModel`
implementation.

```text
PromptStrategySpec
        │
        │ candidate generation
        ▼
PromptStrategy
        │
        └── LanguageModel
```

That makes `PromptStrategy` a runtime artifact rather than durable provider-
independent configuration.

# Prompt Execution

Prompt-backed execution follows a common path.

```text
Prompt
   │
   ▼
LanguageModel.complete()
   │
   ▼
ModelResponse
   │
   ▼
ModelBinding validation
   │
   ▼
StrategyExecutionMetrics
   │
   ▼
StrategyOutcome
```

The provider abstraction supplies the completion.

The prompting layer translates that completion into Azathoth's shared strategy
contract.

# Provider-Neutral Execution Outcome

Provider responses are converted into provider-neutral
`StrategyExecutionMetrics`.

These may include:

```text
provider

model

prompt tokens

completion tokens

total tokens

latency

estimated cost
```

The resulting `StrategyOutcome` can therefore be consumed by execution,
evaluation, scoring, experiments, and optimization without those systems
needing provider-specific response types.

Conceptually:

```text
provider-specific execution
          │
          ▼
     ModelResponse
          │
          ▼
    prompting layer
          │
          ▼
StrategyExecutionMetrics
          │
          ▼
     StrategyOutcome
```

# PromptTemplate

`PromptTemplate` supports context-dependent prompt rendering.

It contains:

```text
text

bindings
```

and is immutable.

Example:

```python
from azathoth.prompting import (
    PromptBinding,
    PromptTemplate,
)

template = PromptTemplate(
    text="Classify this request: {request}",
    bindings=(
        PromptBinding(
            variable_name="request",
            event_type="request.received",
            field_name="text",
        ),
    ),
)
```

The template itself does not execute a model.

It transforms structured `Context` into a provider-neutral `Prompt`.

```text
Context
   │
   ▼
PromptTemplate
   │
   ▼
Prompt
```

# PromptBinding

A `PromptBinding` maps one template variable to one field from the latest
matching context event.

```text
variable_name
      │
      ▼
event_type
      │
      ▼
Context.latest()
      │
      ▼
field_name
      │
      ▼
template value
```

For:

```python
PromptBinding(
    variable_name="request",
    event_type="request.received",
    field_name="text",
)
```

Azathoth resolves:

```text
latest("request.received")
        │
        ▼
payload["text"]
        │
        ▼
{request}
```

This connects context-dependent prompting to the event-backed context
architecture without requiring mutable shared state.

# Prompt Rendering Errors

Prompt rendering fails explicitly when required context is unavailable.

V1 defines:

```text
PromptBindingError

PromptBindingEventNotFoundError

PromptBindingFieldNotFoundError
```

If no matching event exists:

```text
Context.latest(event_type)
        │
        ▼
None
        │
        ▼
PromptBindingEventNotFoundError
```

If the event exists but lacks the configured field:

```text
ContextEvent
    │
    ▼
missing payload[field_name]
    │
    ▼
PromptBindingFieldNotFoundError
```

These failures occur before model execution.

A malformed or incomplete context-dependent prompt therefore does not silently
reach the provider.

# ContextPromptStrategy

`ContextPromptStrategy` combines:

```text
StrategyMetadata

PromptTemplate

LanguageModel

optional ModelRequirements

optional ModelBinding
```

At execution time:

```text
Context
   │
   ▼
PromptTemplate.render()
   │
   ▼
Prompt
   │
   ▼
shared prompt execution
   │
   ▼
StrategyOutcome
```

It implements the same strategy contract as other executable Azathoth
strategies.

The difference is that its prompt is rendered from the supplied execution
context before the language model is called.

# PromptStrategy Versus ContextPromptStrategy

The V1 prompting package supports two executable prompt forms.

```text
PromptStrategy
    already contains a provider-neutral Prompt

ContextPromptStrategy
    renders a PromptTemplate from Context first
```

Both ultimately use the same language-model execution boundary.

```text
PromptStrategy ───────────────┐
                              │
                              ▼
                         execute prompt
                              │
                              ▼
                         LanguageModel

ContextPromptStrategy         ▲
        │                     │
        ▼                     │
PromptTemplate.render() ──────┘
```

# Specification Versus Template

`PromptStrategySpec` and `PromptTemplate` solve different problems.

```text
PromptStrategySpec
    durable specification for a prompt-backed strategy
    includes model-selection authority

PromptTemplate
    context-to-Prompt rendering mechanism
```

A template does not choose a model.

A model-selection object does not render context.

These concerns remain independent.

# Prompting and Context

`azathoth.context` supplies immutable execution state.

Prompt templates read that state through explicit `PromptBinding` objects.

```text
Context
   │
   ▼
PromptBinding
   │
   ▼
PromptTemplate
   │
   ▼
Prompt
```

Prompting does not create a parallel mutable context mechanism.

It consumes the same event-backed context used throughout Azathoth.

# Prompting and Providers

`azathoth.providers` supplies several different things used by prompting:

```text
ModelCatalog
    current normalized metadata

ModelPortfolio
    organizational authorization

LanguageModelRegistry
    executable runtime implementations

ModelRequirements
    provider-neutral requirements

Prompt
    provider-neutral prompt

ModelResponse
    provider-neutral completion result
```

Prompting composes these abstractions.

It does not own them.

# Prompting and Strategies

Prompt-backed execution implements the common strategy contract.

```text
Strategy
   ▲
   │
PromptStrategy
ContextPromptStrategy
```

This lets workflow and execution infrastructure treat language-model-backed
behavior consistently with other strategy implementations.

The prompting package does not need its own execution orchestration framework.

# Prompting and Workflows

Prompt-backed workflow steps use `PromptStrategySpec`.

Conceptually:

```text
WorkflowSpecification
        │
        ▼
WorkflowStepSpecification
        │
        ▼
PromptStrategySpec
        │
        ▼
workflow candidate generation
        │
        ▼
PromptStrategy
        │
        ▼
WorkflowCandidateStep
```

The workflow layer owns:

```text
dependencies
inputs
outputs
conditions
retries
failure policy
workflow execution
```

The prompting layer owns prompt-backed strategy generation and behavior.

# Prompting and Optimization

Portfolio-backed prompt specifications create a legitimate candidate space for
empirical optimization.

```text
PromptStrategySpec
       │
       ▼
PortfolioModelSelection
       │
       ▼
multiple executable PromptStrategy candidates
       │
       ▼
execute
       │
       ▼
evaluate
       │
       ▼
compare empirically
```

The prompting package makes those candidates possible.

It does not decide which candidate is best.

Optimization policy remains in `azathoth.optimization`.

# Prompting and Production

Prompting defines the `FixedModelSelection` primitive used when workflow
production state materializes exact production model intent.

The authority distinction is:

```text
PortfolioModelSelection
    Azathoth may choose among authorized eligible models

FixedModelSelection
    this exact provider/model is required
```

Promotion converts an executable workflow candidate into durable production
configuration with fixed prompt model selections.

Once promoted, production execution follows the production-state model policy
defined by the workflow domain.

Prompting supplies the fixed selection representation.

It does not own production authority.

# No Silent Model Substitution

Prompt candidate generation does not silently reinterpret fixed model intent.

```text
FixedModelSelection("provider/model")
        │
        ├── model exists + executable ──► candidate
        │
        └── otherwise ──────────────────► no candidate
```

It does not do:

```text
fixed model unavailable
        │
        ▼
search portfolio for something similar
```

Any model substitution behavior must be explicit in the architecture that owns
that policy.

# Candidate Generation Is Not Optimization

`generate_prompt_candidates()` determines which runtime prompt strategies can
be constructed under the supplied authority.

It does not score or rank them.

```text
candidate generation
        ≠
optimization
```

Candidate generation answers:

```text
What executable realizations are permitted and possible?
```

Optimization answers:

```text
Which empirically demonstrated candidate should be explored or preferred?
```

Keeping those questions separate prevents selection mechanics from becoming
hidden optimization policy.

# Candidate Generation Is Not Provider Discovery

The `ModelCatalog` is already supplied to candidate generation.

Prompting does not ask providers what models currently exist.

```text
provider discovery
      │
      ▼
ModelCatalog
      │
      ▼
prompt candidate generation
```

That boundary keeps provider synchronization outside runtime strategy
construction.

# Model Metadata Is Not Execution

A `ModelMetadata` object is not enough to build a candidate.

Candidate generation also requires a matching executable `LanguageModel`.

```text
ModelMetadata only
        │
        ▼
not executable

ModelMetadata
      +
LanguageModel
        │
        ▼
PromptStrategy
```

This reinforces the provider ontology:

```text
metadata
    ≠
implementation
```

# Authorization Is Not Executability

Likewise, a model being organizationally authorized does not guarantee a
candidate can execute.

For portfolio selection:

```text
authorized
    +
current
    +
requirements satisfied
    +
runtime implementation exists
        │
        ▼
candidate
```

Every boundary must be satisfied.

# Prompting Is Not Persistence

The prompting package defines domain models and runtime strategy construction.

It does not define repositories.

`PromptStrategySpec` may be persisted as part of a workflow specification, but
workflow persistence belongs to the workflow domain.

Executable `PromptStrategy` objects contain live implementations and are
runtime artifacts.

They are not durable provider-independent configuration.

# V1 Prompting Architecture

The complete V1 prompting path is:

```text
                     DURABLE INTENT

                   PromptStrategySpec
                           │
                           ▼
                     ModelSelection
                      /          \
                     /            \
                    ▼              ▼
       PortfolioModelSelection  FixedModelSelection
                    │              │
                    ▼              │
              ModelPortfolio       │
                    │              │
                    ▼              │
               ModelCatalog ◄──────┘
                    │
                    ▼
           eligible model metadata
                    │
                    ▼
          LanguageModelRegistry
                    │
                    ▼

                   RUNTIME BINDING

                  PromptStrategy
                    │
                    ├── Prompt
                    ├── LanguageModel
                    ├── ModelBinding
                    └── requirements when applicable
                    │
                    ▼

                     EXECUTION

              LanguageModel.complete()
                    │
                    ▼
                ModelResponse
                    │
                    ▼
          ModelBinding validation
                    │
                    ▼
         StrategyExecutionMetrics
                    │
                    ▼
              StrategyOutcome
```

Context-dependent execution adds:

```text
Context
   │
   ▼
PromptTemplate
   │
   ▼
Prompt
   │
   ▼
same execution path
```

# V1 Prompting Principles

The V1 prompting architecture can be summarized as:

```text
prompt intent
    ≠
runtime model implementation

portfolio authority
    ≠
fixed model authority

model metadata
    ≠
model executability

organizational authorization
    ≠
provider availability

candidate generation
    ≠
optimization

prompt execution
    ≠
evaluation

fixed model intent
    ≠
automatic failover
```

The central architectural rule is:

```text
Persist what should happen.

Compose what can execute.

Record exactly what did execute.
```

That allows Azathoth to keep workflow definitions provider-neutral where
appropriate, bind them deterministically to executable runtime capabilities,
and retain exact model identity for empirical evidence and production
materialization.