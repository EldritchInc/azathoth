# ADR 0063: Resolve Production Models From a Fixed Primary and Ordered Substitutes

- Status: Accepted
- Date: 2026-09-02
- Decided in: #71

## Context

ADR 0062 freezes each production prompt step on one exact model. Providers
still have outages and withdraw models, so some workflows need a planned
alternative.

Any alternative must be authorized in advance. Falling back to "whatever the
portfolio would choose" reintroduces the implicit authority that ADR 0062
removed.

## Decision

Production state may record explicit, ordered model substitutes per prompt
step through `WorkflowProductionModelSubstitution`.

`resolve_production_model_selection` resolves a production prompt step
deterministically:

```text
fixed primary model
        │
        ├── executable ──────────► use the primary
        │
        ▼
ordered explicit substitutes
        │
        ├── executable ──────────► use the first executable substitute
        │
        ▼
explicit failure
```

The failures are `ProductionPrimaryModelUnavailableError` and
`ProductionModelSubstitutesUnavailableError`. A production invocation reports
them as the stable error codes `model_unavailable` and
`no_approved_model_substitute`.

Production never selects a model that is not recorded in its state.

Substitutes are a library capability of promotion. The CLI's
`workflow promote` records the materialized primary models only.

## Consequences

### Positive

- Planned fallbacks are possible without implicit authority.
- Resolution is deterministic and auditable from production state alone.

### Negative

- Every substitute must be authorized in advance; there is no automatic
  degradation path.
- CLI operators cannot yet record substitutes.

## Alternatives Considered

### Fall back to portfolio selection

Rejected. Production would select models nobody promoted.

### Fail immediately without substitutes

Rejected. Planned resilience is a legitimate production requirement.
