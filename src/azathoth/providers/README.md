# Providers

`azathoth.providers` defines Azathoth's provider-neutral model ontology,
discovery infrastructure, organizational model authorization, executable model
registry, and provider integrations.

The package deliberately separates several concepts that are often collapsed
into a single "available models" collection.

```text
provider
   │
   │ discovery
   ▼
ProviderModel
   │
   ├──────────────► ProviderModelObservation
   │                    historical evidence
   │
   │ normalization
   ▼
ModelMetadata
   │
   ▼
ModelCatalog
   │
   │ intersect with
   ▼
ModelPortfolio
   │
   ▼
authorized current models
```

Executable model implementations are represented separately:

```text
LanguageModelRegistry
        │
        ▼
process-local executable models
```

These boundaries distinguish provider truth, historical observation,
organizational authorization, normalized runtime metadata, and executable
process state.

## Provider-Neutral Identity

Models are identified throughout Azathoth using provider-qualified identifiers:

```text
provider/model
```

Both `ModelMetadata` and `ModelPortfolioEntry` expose this identity through
their `identifier` properties.

Provider qualification prevents model-native names from becoming globally
ambiguous and allows model policy to remain independent of any single provider.

## Provider Model State

`ProviderModel` describes facts currently reported by a model provider.

It includes:

- provider identity
- provider-native model identity
- display name
- supported input modalities
- supported output modalities
- capabilities
- context-window limits
- maximum output limits
- pricing

A `ProviderModel` represents current provider truth at discovery time.

It is not organizational authorization.

It is not historical evidence.

It is not an executable language model implementation.

Provider model facts expose a deterministic `fingerprint` derived from their
normalized content.

## Provider Discovery

`ProviderModelDirectory` defines the provider-neutral contract for discovering
current provider model state.

A directory exposes:

```text
provider
models()
model(identifier)
```

The directory answers what the external provider currently exposes.

Provider-specific implementations translate external provider APIs into
`ProviderModel` values.

V1 includes `OpenRouterModelDirectory` for OpenRouter discovery.

Provider discovery can fail explicitly with `ModelDiscoveryError`.

## Provider Observations

External model catalogs change over time.

`ProviderModelObservation` records provider model facts observed by Azathoth at
one moment.

```text
ProviderModel
      │
      ▼
ProviderModelObservation
      │
      ▼
ProviderModelObservationRepository
```

An observation contains:

- a unique observation identity
- an observation timestamp
- the complete normalized `ProviderModel`

Observations are historical evidence.

They are not the current model catalog.

## Change-Aware Observation

`ProviderModelObserver` coordinates discovery with durable observation history.

For each discovered model it compares the current provider-model fingerprint
with the latest persisted observation.

```text
discover model
     │
     ▼
compare fingerprint
     │
     ├── unchanged ──► reuse latest observation
     │
     └── changed ────► persist new observation
```

The result is represented by `ProviderModelObservationUpdate`, which contains
the observation and whether a new historical record was created.

The observer also validates that:

- discovered models belong to the expected provider
- a provider directory does not return duplicate model identities

Observation history therefore records meaningful provider-state changes
without becoming the source of current runtime truth.

## Current Model Catalog

`ModelCatalog` is an immutable inventory of normalized model metadata available
to Azathoth.

It contains ordered `ModelMetadata` values and rejects duplicate
provider-qualified identifiers.

The catalog supports:

- lookup by provider-qualified identifier
- provider-specific filtering
- requirement-based queries
- deterministic identifier ordering

```text
ModelCatalog
    │
    ├── get(identifier)
    ├── models_for_provider(provider)
    └── find(query)
```

`ModelMetadata` describes normalized model identity and capabilities.

It includes:

- provider
- model
- display name
- input modalities
- output modalities
- capabilities
- context-window limits
- maximum output limits
- pricing

`ModelCatalog` describes model metadata.

It does not contain executable model clients.

## Building Current Catalogs From Providers

`ProviderModelCatalogSynchronizer` builds a current runtime catalog from
provider discovery.

```text
ProviderModelDirectory
        │
        ▼
ProviderModelObserver
        │
        ├────────────► observation history
        │
        ▼
ProviderModel
        │
        ▼
model_metadata_from_provider_model
        │
        ▼
ModelMetadata
        │
        ▼
ModelCatalog
```

The synchronizer uses current discovery results to construct the returned
catalog.

Historical observations do not determine which models remain current.

If a model disappears from current provider discovery, its historical
observations may remain durable while the model is absent from the newly
constructed current catalog.

This distinction is intentional:

```text
observation history ≠ current availability
```

## Durable Model Metadata

Azathoth also defines `ModelRepository` for durable `ModelMetadata`
persistence.

`ModelCatalogLoader` reconstructs an immutable catalog from repository state.

Repository implementations include:

- `InMemoryModelRepository`
- `SQLiteModelRepository`

This persistence boundary stores normalized model metadata without owning
provider discovery or executable provider clients.

## Model Requirements and Queries

Model eligibility is expressed through provider-neutral requirements.

`ModelRequirements` describes capability requirements used when selecting
models for executable strategies.

`ModelQuery` provides catalog filtering across:

- providers
- required capabilities
- required input modalities
- required output modalities
- minimum context-window size
- minimum output size
- maximum input pricing
- maximum output pricing
- known-pricing requirements

Queries operate on normalized `ModelMetadata`.

They do not call providers and do not change authorization policy.

## Organizational Authorization

`ModelPortfolio` describes the ordered models an organization has explicitly
authorized for general Azathoth selection.

A portfolio contains immutable `ModelPortfolioEntry` values.

Each entry identifies exactly one:

```text
provider/model
```

The distinction between catalog and portfolio is fundamental:

```text
ModelCatalog
    what models are available

ModelPortfolio
    what models Azathoth is authorized to select
```

A model being available does not authorize Azathoth to choose it.

A model being authorized does not guarantee that it is currently available.

## Portfolio Persistence

`ModelPortfolioRepository` persists organizational model authorization.

Implementations include:

- `InMemoryModelPortfolioRepository`
- `SQLiteModelPortfolioRepository`

`ModelPortfolioLoader` reconstructs the immutable ordered portfolio from
repository state.

Portfolio authorization is durable policy.

It is independent of provider discovery.

## Authorized Current Models

`model_catalog_for_portfolio` explicitly composes current availability with
organizational authorization.

```text
ModelCatalog
 current models
      │
      ├──────────┐
      │          │
      │     ModelPortfolio
      │      authorized models
      │          │
      └────┬─────┘
           ▼
    ModelCatalog
 authorized AND current
```

Portfolio order determines the order of the resulting catalog.

Authorized models that are absent from the current catalog are omitted.

Current models that are absent from the portfolio are not added.

This intersection is explicit rather than implicit.

## Model Selection Authority

Azathoth distinguishes between models that may be selected dynamically and
models that have already been fixed by durable workflow intent.

General candidate generation may use organizational portfolio authorization
when resolving model requirements.

Production workflow prompt steps use exact fixed model selections materialized
during explicit promotion.

Therefore:

```text
development / experimentation
    model requirements
          +
    current catalog
          +
    portfolio authorization
          │
          ▼
    executable selection
```

while production uses:

```text
WorkflowProductionState
          │
          ▼
fixed primary model
          │
          ├── executable ──► use primary
          │
          ▼
explicit ordered production substitutes
```

The provider package supplies model truth and authorization primitives.

It does not silently expand production model authority.

## Executable Language Models

`LanguageModel` is the provider-neutral protocol for executable language model
implementations.

Its execution boundary is intentionally small:

```python
async def complete(
    prompt: Prompt,
) -> ModelResponse: ...
```

Provider-specific implementations satisfy this protocol.

V1 includes:

- `OpenRouterLanguageModel`
- `DeterministicLanguageModel`

`DeterministicLanguageModel` provides predictable execution for tests and local
composition.

## Language Model Registry

`LanguageModelRegistry` contains process-local executable `LanguageModel`
implementations keyed by provider-qualified identifier.

This is distinct from `ModelCatalog`.

```text
ModelCatalog
    metadata describing models

LanguageModelRegistry
    executable implementations
```

A model may therefore be represented in metadata without an executable client
being present in a particular process.

Runtime generation and production resolution can require both current metadata
and executable registry presence before a model can actually execute.

## Provider-Neutral Requests and Responses

`Prompt` represents rendered prompt text sent to a language model.

`ModelRequest` represents a provider-neutral request.

`ModelResponse` records provider-neutral execution evidence including:

- response text
- provider
- model
- resolved model when supplied
- prompt token count
- completion token count
- total token count
- latency
- estimated cost

These values allow higher-level Azathoth systems to reason about model
execution without depending on provider-specific response formats.

## Model Executor

`ModelExecutor` executes durable provider-neutral `ModelRequest` values through
a `LanguageModel`.

The executor validates whether request controls are supported by the current
provider boundary before invoking the language model.

Unsupported controls fail explicitly with
`UnsupportedModelRequestError`.

Provider execution failures use `ModelExecutionError`.

The execution abstraction therefore avoids silently ignoring unsupported
request semantics.

## OpenRouter

V1 includes an OpenRouter integration for both execution and model discovery.

`OpenRouterConfiguration` contains:

- API key
- API base URL
- request timeout

`OpenRouterModelDirectory` translates OpenRouter's current model catalog into
provider-neutral `ProviderModel` values.

`OpenRouterLanguageModel` translates prompt execution into provider-neutral
`ModelResponse` evidence.

`OpenRouterModelRegistryLoader` constructs executable OpenRouter language model
implementations for OpenRouter models represented in a `ModelCatalog`.

Provider-specific translation remains behind the provider-neutral domain
interfaces.

## Persistence Boundaries

The provider package defines independent persistence contracts for:

```text
ModelRepository
    normalized model metadata

ModelPortfolioRepository
    organizational authorization

ProviderModelObservationRepository
    historical provider observations
```

These repositories intentionally store different kinds of truth.

They should not be treated as interchangeable model inventories.

## Architectural Boundaries

The V1 provider architecture deliberately maintains the following distinctions:

```text
ProviderModel
    current facts reported by a provider

ProviderModelObservation
    immutable historical provider evidence

ModelMetadata
    normalized provider-neutral model metadata

ModelCatalog
    immutable model inventory

ModelPortfolioEntry
    durable authorization of one model

ModelPortfolio
    ordered organizational authorization

LanguageModel
    executable provider-neutral model protocol

LanguageModelRegistry
    process-local executable implementations
```

The most important consequences are:

```text
history ≠ current provider state

availability ≠ authorization

metadata ≠ executable implementation

authorization ≠ production execution authority
```

These boundaries allow external provider state, organizational policy,
runtime composition, experimentation, optimization, and production deployment
to evolve independently without silently changing what Azathoth is authorized
to execute.