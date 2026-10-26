# ADR 0060: Build Runtime Model Catalogs From Current Provider State

- Status: Accepted
- Date: 2026-08-30
- Decided in: #66

## Context

ADR 0048 persisted configured model metadata so runtimes could be
reconstructed. Persisted metadata, however, describes what was configured,
not what a provider offers now. A runtime built only from it can select a
model the provider no longer serves, or miss one it now does.

ADR 0057 records provider observations, and deliberately keeps them out of
current selection.

## Decision

`ProviderModelCatalogSynchronizer` builds the runtime's current `ModelCatalog`
from current provider discovery:

```text
ProviderModelDirectory
        │
        ▼
ProviderModelObserver ─────► observation history
        │
        ▼
ProviderModel
        │
        ▼
model_metadata_from_provider_model
        │
        ▼
ModelCatalog (current)
```

The catalog contains exactly what current discovery returned. A model absent
from discovery is absent from the catalog, even when its observation history
remains.

The CLI bootstrap builds this catalog when provider credentials are
configured. Without `OPENROUTER_API_KEY`, the current catalog is empty, so
provider-free commands and tool-only workflows still work.

## Consequences

### Positive

- Runtime selection reflects what providers serve now.
- Observation history and current availability stay separate.
- Tool-only workflows need no provider credentials.

### Negative

- Building a runtime with credentials makes provider requests.
- A provider outage empties the current catalog for that process.

## Alternatives Considered

### Build the runtime catalog from persisted metadata

Rejected. It would select models providers no longer serve.

### Build it from the latest observations

Rejected for the reason in ADR 0057: history is not availability.
