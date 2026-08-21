# ADR 0048: Persist Configured Model Metadata

- Status: Accepted
- Date: 2026-08-20

## Context

Azathoth separates three concerns involved in model-backed execution.

```text
Workload Requirements
        │
        ▼
ModelRequirements

Configured Model Knowledge
        │
        ▼
ModelMetadata / ModelCatalog

Executable Runtime
        │
        ▼
LanguageModelRegistry
```

`ModelRequirements` describes what kind of model a workload needs.

`ModelMetadata` describes configured models, including identity, capabilities,
modalities, context limits, and pricing.

`LanguageModelRegistry` provides executable runtime implementations for
provider-qualified model identifiers.

`ModelCatalog` is an immutable inventory of configured `ModelMetadata`.

Before this decision, model catalogs had to be reconstructed from application
code each time a process started.

That made workflow specifications durable while leaving the configured model
universe dependent on process-local construction.

## Decision

Azathoth persists configured `ModelMetadata` through a storage-neutral
`ModelRepository`.

```text
ModelMetadata
      │
      ▼
ModelRepository
      │
      ├── InMemoryModelRepository
      │
      └── SQLiteModelRepository
```

`ModelCatalogLoader` reconstructs an immutable `ModelCatalog` from repository
state.

```text
ModelRepository
      │
      ▼
ModelCatalogLoader
      │
      ▼
ModelCatalog
```

Persistence remains below model discovery and candidate generation.

## Persistence Unit

The persisted domain object is `ModelMetadata`.

```text
ModelMetadata
├── provider
├── model
├── display name
├── modalities
├── capabilities
├── context window
├── maximum output size
└── pricing
```

Executable runtime objects are not persisted.

This includes:

- `LanguageModel`;
- `OpenRouterLanguageModel`;
- HTTP clients or transports;
- `LanguageModelRegistry`; and
- other process-local provider implementations.

Those objects are reconstructed at runtime.

## Credentials Are Not Model Metadata

Provider credentials are intentionally excluded from model persistence.

For example, `OpenRouterConfiguration` contains provider access configuration,
including the API key.

```text
OpenRouterConfiguration
├── api key
├── base URL
└── timeout
```

This configuration is runtime state.

It is not stored in `ModelRepository`.

```text
ModelRepository
    ✓ model identity
    ✓ capabilities
    ✓ context limits
    ✓ pricing

    ✗ API keys
    ✗ authorization headers
    ✗ HTTP clients
```

This keeps durable model knowledge separate from sensitive provider access.

## Repository Identity

Configured models are identified by their provider-qualified model identifier.

```text
provider/model
```

For example:

```text
openrouter/example-model
```

Persisting another model with the same identifier is rejected rather than
replacing the existing configuration.

Model configuration is therefore append-only at this persistence boundary.

## Deterministic Ordering

Repositories preserve insertion order.

`ModelCatalogLoader` preserves that order when reconstructing a catalog.

```text
Repository
├── model A
├── model B
└── model C
        │
        ▼
ModelCatalog
├── model A
├── model B
└── model C
```

This matters because catalog order is part of deterministic candidate
generation when multiple models satisfy the same workload requirements.

Persistence must not introduce a new ordering policy.

## Provider Queries

`ModelRepository` supports retrieving configured models belonging to one
provider.

```text
ModelRepository
        │
        ▼
models_for_provider("openrouter")
        │
        ▼
configured OpenRouter metadata
```

This supports runtime assembly such as `OpenRouterModelRegistryLoader`.

Capability, pricing, modality, and context filtering remain responsibilities of
`ModelCatalog` and `ModelQuery` after reconstruction.

## SQLite Representation

SQLite stores the canonical serialized `ModelMetadata`.

```text
ModelMetadata
      │
      ▼
model_dump_json()
      │
      ▼
models
      │
      ▼
model_validate_json()
      │
      ▼
ModelMetadata
```

The table also stores queryable identity and provider fields.

```text
models
├── sequence
├── identifier
├── provider
└── payload
```

`sequence` preserves insertion order.

`identifier` supports direct lookup.

`provider` supports provider-specific repository queries.

Detailed model characteristics remain inside the canonical serialized payload
and are queried after reconstruction through the provider domain.

## Reconstructed Model Catalogs

Persisted model metadata reconstructs through the same domain type used by
direct application configuration.

```text
SQLite
  │
  ▼
SQLiteModelRepository
  │
  ▼
ModelCatalogLoader
  │
  ▼
ModelCatalog
```

There is no separate persisted-model execution path.

Higher-level systems receive the same immutable `ModelCatalog` regardless of
whether its metadata originated from:

- application configuration;
- memory persistence;
- SQLite persistence; or
- another repository implementation.

## Runtime Reconstruction

Durable model knowledge and runtime execution remain separate.

For OpenRouter:

```text
Persisted ModelMetadata
        │
        ▼
ModelCatalog
        │
        +
OpenRouterConfiguration
        │
        ▼
OpenRouterModelRegistryLoader
        │
        ▼
LanguageModelRegistry
```

The model catalog supplies model identity and characteristics.

The OpenRouter configuration supplies provider access.

The runtime loader creates executable model implementations.

## Durable Workflow Resolution

Workflow specifications already persist model-independent
`ModelRequirements`.

With durable model catalogs, both sides of workflow model resolution survive
process restart.

```text
WorkflowSpecification
        │
        └── ModelRequirements
                ✓ durable

ModelRepository
        │
        └── ModelMetadata
                ✓ durable

              restart
                │
                ▼

WorkflowCatalogLoader
        +
ModelCatalogLoader
        │
        ▼
candidate generation
        │
        ▼
concrete ModelBinding
```

Runtime provider implementations are attached only after reconstruction.

## Heterogeneous Resolution After Restart

A reconstructed workflow may contain multiple prompt-backed steps with
different requirements.

A reconstructed model catalog may contain models with different capabilities
and prices.

Candidate generation continues to resolve each step independently.

```text
Persisted Workflow
│
├── Step A
│   └── inexpensive model required
│
└── Step B
    └── structured output required

Persisted Model Catalog
│
├── cheap model
└── structured-output model

            │
         restart
            │
            ▼

Step A → cheap model
Step B → structured-output model
```

Persistence therefore does not collapse heterogeneous model execution into one
global model.

## Consequences

### Positive

- Configured model inventories survive process restarts.
- Model capabilities and pricing remain reproducible.
- Catalog ordering remains deterministic.
- Workflow model requirements can be resolved against durable model knowledge.
- OpenRouter runtime assembly can operate from reconstructed catalogs.
- Multiple models remain independently configurable.
- Provider credentials remain outside model persistence.
- Runtime provider objects remain process-local.
- Persistence introduces no model ranking or optimization policy.

### Negative

- Applications still need runtime provider configuration after restart.
- Persisted metadata may become stale relative to a provider's current model
  offerings.
- Updating an existing model configuration requires an explicit future mutation
  or versioning policy rather than silent replacement.
- SQLite stores detailed metadata as serialized JSON rather than normalized
  relational fields.
- Provider-specific model discovery is not introduced by this decision.

## Alternatives Considered

### Persist ModelCatalog Directly

Rejected.

The catalog is a reconstructed immutable view over configured model metadata.

Persisting individual `ModelMetadata` records gives repositories useful
identity and provider queries while preserving the catalog as a domain
projection.

### Persist LanguageModelRegistry

Rejected.

A registry contains executable process-local runtime implementations.

Those implementations may contain clients, transports, credentials, and other
runtime dependencies that should not be serialized.

### Persist OpenRouterConfiguration With Model Metadata

Rejected.

Provider credentials and model metadata have different lifecycles and security
requirements.

Model persistence must not become secret storage implicitly.

### Rebuild Model Metadata in Application Code

Rejected as the only durable mechanism.

Workflow specifications can survive process restart, so the model knowledge
required to resolve them should also be capable of surviving restart.

### Query Capabilities Directly in SQLite

Rejected for this persistence boundary.

Capability and pricing filtering already belong to `ModelQuery` and
`ModelCatalog`.

The repository persists and reconstructs configured models; it does not replace
the provider discovery domain.

## Result

Azathoth now has durable model configuration beneath the existing provider
runtime.

```text
                  SQLite
                    │
                    ▼
            ModelRepository
                    │
                    ▼
           ModelCatalogLoader
                    │
                    ▼
              ModelCatalog
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
 model discovery       runtime assembly
          │                   │
          └─────────┬─────────┘
                    ▼
           candidate generation
                    │
                    ▼
              ModelBinding
                    │
                    ▼
               execution
```

Persistence stores model knowledge.

Runtime configuration supplies provider access.

Candidate generation resolves concrete models.

Model catalog persistence introduces no ranking or optimization policy.