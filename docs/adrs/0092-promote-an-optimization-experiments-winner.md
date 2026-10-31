# ADR 0092: Promote an Optimization Experiment's Winner

- Status: Accepted
- Date: 2026-10-31
- Decided in: #109

## Context

`workflow promote <WORKFLOW_ID>` promotes the configured candidate: each
prompt step bound to the first authorized model that fits it, in portfolio
order. That is the right default for a workflow nobody has optimized, and
deploying a workflow never requires optimizing it.

When an operator has optimized the workflow and likes the winner, though,
1.0 offered no direct way to deploy it. The workaround was to export the
workflow, pin each prompt step to the winner's model, import the result as a
new revision, benchmark it, and promote that.

The evidence to do better is already recorded. An experiment record ranks
its observations, and the top-ranked observation carries the winner's
candidate signature: the workflow ID, the revision it was generated from,
and one strategy ID per step. A generated prompt strategy's ID is derived
from the step's strategy ID and the provider-qualified model identifier, so
the same step on the same model always has the same ID.

## Decision

`workflow promote` takes an optional `--experiment <EXPERIMENT_ID>`:

```bash
azathoth workflow promote <WORKFLOW_ID> --experiment <EXPERIMENT_ID>
```

It promotes the experiment's top-ranked candidate. The ID to pass is the
`Winning Experiment ID` the optimize report ends with (ADR 0091).

The winning candidate is rebuilt, not trusted. Starting from the configured
candidate of the workflow's current revision, each step keeps its strategy
when the strategy ID matches the winner's. A prompt step whose ID differs is
matched against the candidates generated for it over the currently
authorized models. The rebuilt candidate's signature must equal the
winner's exactly, or nothing is promoted. Promotion then pins every prompt
step to the model it was measured on, exactly as it does for the configured
candidate.

The command refuses, and says why, when:

- no experiment has the ID;
- the experiment's winner is not the named workflow;
- the winner was measured on a different revision than the workflow's
  current one, or the record names no revision;
- a winning step cannot be rebuilt, because its model is no longer in the
  catalog or no longer authorized.

A different revision is refused rather than promoted. If the operator
imported a new revision after optimizing, the experiment measured something
else. To keep the optimizer's choices, the operator pins those models in the
new revision deliberately, or optimizes the new revision. Either way the new
revision can be promoted directly; optimizing is never required.

`workflow promote <WORKFLOW_ID>` without `--experiment` is unchanged.

The production revision records what was promoted, as it always has: the
specification with every prompt step pinned, and the specification revision.
It does not record the experiment. The pinned models and the revision
identify the deployment, and promotion with or without an experiment produces
the same kind of production state.

## Consequences

### Positive

- The optimizer's winner can be deployed with one command, copying the ID
  from the optimize report.
- What is deployed is exactly what was measured: the same revision and the
  same model on every step, checked by signature.
- Deploying a workflow still never requires optimizing it.

### Negative

- A winner can only be promoted while its revision is current and its
  models are still authorized. After a re-import, the operator pins the
  models by hand or optimizes again.
- Only the top-ranked candidate can be promoted this way. Promoting a
  runner-up still means pinning its models by hand.

## Alternatives Considered

### Promote the measured revision even when a newer one exists

Rejected. It would deploy a specification that is no longer the workflow's
current one and silently discard whatever the newer revision changed.

### Promote any observation, with `--candidate <OBSERVATION_ID>`

Deferred. The winner is the case operators need now, and the same rebuild
can serve a runner-up later.

### Record the source experiment on the production revision

Rejected. Production state is the same whether or not the operator
optimized, and the pinned models and revision already identify what was
deployed.

### Promote from `workflow optimize` directly

Rejected. Optimizing records evidence and never changes production.
Promotion stays a separate, deliberate step.
