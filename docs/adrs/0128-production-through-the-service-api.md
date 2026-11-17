# ADR 0128: Production Through the Service API

- Status: Accepted
- Date: 2026-11-17

## Context

The command line promotes a workflow, shows what is in production, lists
production revisions and invocations, and resumes a stopped invocation:
`workflow promote`, `workflow production`, `workflow revisions`, `workflow
invocations` and `invocation resume`. The service API reaches only two of
those things, `runs.invoke` and `invocations.get` (ADR 0120). The editor
drives Azathoth only through the service API, so today it can build and run
a workflow but cannot put it into production or see what production does
with it.

Nothing can undo a promotion either. Promoting saves an immutable
`WorkflowProductionRevision` and sets the active `WorkflowProductionState`;
the active revision is the newest whose state equals the active one. A
promotion that went wrong is put right only by promoting again, which
builds a candidate from the workflow as it is now, not as it was when
production last worked.

A production revision also says nothing of who made it, though every
workflow revision has recorded its author since ADR 0122.

## Decision

### Who promoted, and what a revision restores

A `WorkflowProductionRevision` gains two optional fields:

- `author`, the person who promoted or rolled back, told as the instance
  tells who imports (ADR 0122): the author the instance was opened with,
  then `AZATHOTH_AUTHOR`, then the operating system's username;
- `restores`, the ID of the earlier production revision a rollback brought
  back, absent for a promotion.

Revisions are kept as their JSON, so neither field needs a new schema
version, and a revision saved before 1.5 reads back with neither. The
schema stays at version 7.

### Rolling back

`azathoth workflow rollback WORKFLOW_ID [--to PRODUCTION_REVISION_ID]`
returns a workflow's production to an earlier production revision's state.
Without `--to`, it is the revision before the active one, newest first.

A rollback never edits history. It saves a new production revision whose
state is the earlier revision's, and whose `restores` names it, and makes
that state active. Promotions and rollbacks are then one timeline, in the
order they happened, which is what a change history reports.

A rollback is refused, and nothing changes, when:

- the workflow has no production revision before the active one, or none at
  all;
- `--to` names a revision of another workflow, or none;
- `--to` names the revision whose state is already active;
- a step of the state to restore has no model the portfolio still
  authorizes, neither its fixed model nor any substitute production
  approved for it. Deauthorizing a model checks only active production, so
  an earlier state may name a model since removed; its message names the
  step and the model, and says to authorize it again first.

```text
Workflow <WORKFLOW_ID> has no earlier production revision to roll back to.
Production revision <REVISION_ID> is already active for workflow <WORKFLOW_ID>.
Step <STEP_ID> of production revision <REVISION_ID> uses <MODEL>, which the portfolio no longer authorizes; authorize it again before rolling back to it.
```

`workflow revisions` and `workflow production` show each revision's author,
and what a rollback restored.

### `instance.production`

The service API gains a `production` collection:

| Call | Returns |
| --- | --- |
| `production.get(workflow_id)` | The `ProductionState`: the active production revision, the workflow revision it was promoted from, its model substitutions, its author and when it was made; `None` when the workflow is not in production. |
| `production.revisions(workflow_id, limit=None)` | Its `ProductionRevisionSummary` items, newest first, the active one marked, each with its author and what it restores. |
| `production.promote(workflow_id, experiment_id=None)` | The `ProductionRevisionSummary` it saved, as `workflow promote` does, with an experiment's winner when one is named (ADR 0092). |
| `production.roll_back(workflow_id, to=None)` | The `ProductionRevisionSummary` it saved, as `workflow rollback` does. |

A workflow that is neither configured nor has production history raises
`NotFoundError`, as the command line refuses it. The new refusals are
`ApiError`s with codes of their own:

| Error | Code | When |
| --- | --- | --- |
| `WorkflowResultMissingError` | `workflow_result_missing` | The workflow declares no result, so it cannot be promoted. |
| `ExperimentNotFoundError` | `experiment_not_found` | No experiment has the ID named; a `NotFoundError` too. |
| `CandidateRebuildError` | `candidate_rebuild` | An experiment's winner cannot be rebuilt from the workflow's latest revision with the models authorized now. |
| `NothingToRollBackToError` | `nothing_to_roll_back_to` | There is no earlier revision, or the one named is already active; a `ConflictError` too. |
| `ModelNotAuthorizedError` | `model_not_authorized` | A step of the state to restore has no model the portfolio authorizes; a `ConflictError` too. |

### Invocations

`instance.invocations` gains two calls:

| Call | Returns |
| --- | --- |
| `invocations.list(workflow_id, limit=None)` | Its `InvocationSummary` items, newest first: the invocation, when it was made, its status, its caller metadata, its sensitivity label, and its run's ID when it has one. |
| `invocations.resume(invocation_id, on_event=None, cancel=None)` | The `InvocationOutcome`, as `invocation resume` does: the invocation's run continues from its journal, reporting events as `runs.invoke` does. |

Who may read or resume which invocation is still the caller's to decide,
as ADR 0120 leaves it; on a remote, it is the policy's, through the
`read_runs`, `invoke` and `promote` actions of ADR 0127.

## Consequences

- The editor can promote, roll back, invoke, and show a workflow's
  production and its invocations, through the service API alone.
- A promotion that went wrong is undone in one step, to a state that
  worked, without promoting the workflow's current revision.
- Every production revision made from 1.5 on says who made it; those made
  before say nobody, as revisions imported before 1.4 do.
- Rolling back to a state whose models were deauthorized means authorizing
  them again first, so a rollback never puts into production a model the
  instance no longer allows.

## Alternatives Considered

### Setting the earlier state active without a revision

Making an earlier revision's state active again, and saving nothing, would
need no new revision, but the active revision would then be found by
matching states, and the timeline would show the earlier promotion as
active again with nothing saying when production changed, or who changed it.

### Rolling back by promoting an earlier workflow revision

Promoting an earlier workflow revision would build a new candidate from it
with today's catalog and portfolio, which may choose other models than the
ones production ran. A rollback restores exactly what ran.

### Requiring `--to`

Naming the revision every time would make the commonest rollback, undoing
the last promotion, the slowest. `--to` is there for any other.
