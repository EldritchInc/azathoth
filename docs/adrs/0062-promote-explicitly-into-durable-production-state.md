# ADR 0062: Promote Explicitly Into Durable Production State

- Status: Accepted
- Date: 2026-09-02
- Decided in: #70, #71, #76

## Context

Optimization finds candidates that perform well. That alone must never change
what production runs: an optimizer's winner may be cheaper but riskier, may
have been judged on an unrepresentative benchmark, or may simply not be wanted
yet.

Production also cannot depend on portfolio selection. If production asked the
portfolio which model to use on each call, production behavior would change
whenever the portfolio or a provider catalog changed.

## Decision

Moving a workflow into production is one explicit operation, promotion.

`promote_workflow_candidate` turns one explicitly selected executable
candidate into a durable `WorkflowProductionState`:

```text
WorkflowSpecification + WorkflowCandidate
        │
        ▼
materialize_workflow_candidate
        │
        ▼
WorkflowProductionState
```

Materialization records each prompt step's bound model as an exact
`FixedModelSelection`. Production therefore keeps running the model that was
promoted, whatever later happens to the portfolio.

`WorkflowProductionState` is the durable description of what production
executes now: the materialized specification, explicit model substitutions
(ADR 0063) and explicit emissions (ADR 0065).

The CLI exposes promotion as:

```bash
azathoth workflow promote <WORKFLOW_ID>
```

Optimization never promotes. Neither `workflow optimize` nor any optimizer
writes production state.

## Consequences

### Positive

- Production changes only when someone deliberately promotes.
- Production model choice is frozen at promotion time.
- Optimization can be run freely without production risk.

### Negative

- Improvements reach production only through a manual step.
- A promoted model that a provider withdraws fails until it is substituted or
  the workflow is promoted again.

## Alternatives Considered

### Deploy the optimizer's winner automatically

Rejected. Optimization would silently hold production authority.

### Resolve production models through the portfolio at call time

Rejected. Production behavior would follow portfolio and provider churn.
