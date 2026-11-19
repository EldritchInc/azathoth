# ADR 0131: Optimization Through the Service API

- Status: Accepted
- Date: 2026-11-19

## Context

The service API (ADR 0120) promotes an experiment's winner into production
(ADR 0128), but nothing else about optimization reaches it. `workflow
optimize` runs model-substitution optimization against a benchmark (ADRs
0051 and 0072) and prints the session once it ends; `workflow experiments`
lists a workflow's experiments, and `experiment show` prints one with every
candidate ranked (ADR 0069). Each holds its own logic, and none can be
watched as it runs or stopped part way.

The editor drives Azathoth only through the API, so it can promote an
experiment's winner but cannot start the optimization that finds it, watch
it, or read the experiment it would promote.

Nor can any surface say what promoting a winner would change. An
experiment ranks candidates by their scores, which are normalized against
the session's targets (ADR 0030), so it says which candidate is best but
not what it saves: the dollars and seconds a run costs are in the case runs
the experiment kept, and no command adds them up or sets the winner beside
what production runs now. ADR 0127's `optimize` action promises "Optimize a
workflow", and a person deciding whether to promote needs both answers.

## Decision

Every call here is an addition to the 1.x service API, on two new
namespaces, `instance.experiments` and `instance.optimization`. `workflow
experiments` and `experiment show` become thin wrappers over the same
calls, as production's, the judges' and benchmarks' commands did (ADRs
0128, 0129 and 0130), and their output is unchanged. One new command,
`experiment compare`, gives comparing its command line. Each call is one of
the 0127 catalog's named actions, for a remote's policy in 1.6.

`workflow optimize` is the exception, as `run resume` and `benchmark run`
are (ADRs 0129 and 0130): it loads the runtime from the command line's own
provider discovery and renders the session as it always has, so it keeps
its own reporting, and optimizes through the same function
`optimization.optimize` calls, with the same checks before any candidate
runs.

### Reading experiments

| Call | Returns | Action |
| --- | --- | --- |
| `experiments.list(workflow_id, limit=None)` | A workflow's experiments, newest first | `read_runs` |
| `experiments.get(experiment_id)` | One, with every candidate ranked and every case | `read_runs` |

An `ExperimentSummary` has the experiment's ID, its workflow, when it was
recorded, the benchmark it ran and the revision holding that content, its
label, how many candidates and cases it held, and its winner's overall
score. An `ExperimentDetail` adds every candidate in rank order: its rank,
each step's strategy and model, its scorecard, how many cases it passed,
its judge calls and their cost, and each case's run, evaluation and
outcome. An experiment recorded before benchmark-driven optimization (ADR
0072) has no benchmark, no case IDs and unknown outcomes; each reads as
`None`, as `experiment show` renders it. An unknown experiment is
`experiment_not_found`.

### Optimizing

| Call | Returns | Action |
| --- | --- | --- |
| `optimization.optimize(workflow_id, benchmark_id, *, target_latency_seconds, target_cost_usd, generations=1, on_event=None, cancel=None)` | An `OptimizationSummary` | `optimize` |

An `OptimizationSummary` has every generation, each with the experiment
that measured its population, its winner and the size of the population it
proposed; the final evaluation's experiment (ADR 0091), or `None` with why
it did not run; the winning experiment; and the session's judge calls and
cost. Every experiment it names is recorded, so `experiments.get` reads it.

`optimize` checks everything before any candidate runs, as `workflow
optimize` does: an unknown workflow or benchmark is `not_found`; a
benchmark with no cases, a comparison no evaluator supports, a target that
is not above zero, or fewer than one generation is `invalid_argument`; a
workflow that declares no result is `workflow_result_missing`; and a
semantic case with no usable judge is `judge_unavailable` (ADR 0130).

**Optimization runs live.** `on_event` receives, on the caller's thread:

| Event | Carries |
| --- | --- |
| `generation_started` | The generation, and how many candidates it runs |
| `candidate_finished` | The generation, the candidate's signature, how many cases it passed of how many, and its overall score |
| `generation_finished` | The generation, its experiment, its winner, and how many candidates it proposes next |

The final evaluation is told as one more generation, numbered after the
last. `cancel` is checked between candidates. A cancelled session keeps
every experiment it finished, and every case run, as any run is kept;
records no experiment for a generation it did not finish; and raises
`RunCancelledError`, as a cancelled run and a cancelled benchmark do. The
experiments it finished are listed by `experiments.list`, so nothing it
learned is lost, but a session half run is never reported as a result.

### Comparing the winner, and what it saves

| Call | Returns | Action |
| --- | --- | --- |
| `experiments.compare(experiment_id)` | An `ExperimentComparison` | `read_runs` |
| `experiments.promotable(experiment_id)` | A `Promotability` | `read_runs` |

**The winner is set beside a baseline.** The baseline is what production
runs now, when its candidate is among the experiment's candidates, since
promoting the winner replaces it. Otherwise it is the workflow's
configured candidate, the one optimization starts from, when the
experiment holds it. The comparison names which it is, `production` or
`configured`; an experiment holding neither, or whose winner is its
baseline, compares nothing and says so, with `baseline` `None`.

An `ExperimentComparison` has, for the winner and the baseline:

- each step's strategy and model, side by side, and which steps differ;
- each part of their scorecards;
- every case: whether each passed, and each score;
- what a run cost, in dollars, and how long it took, in seconds, each the
  mean over the experiment's case runs, as the scorer measured them (ADR
  0030). A run whose cost is unknown, because a model's pricing is unknown,
  makes its side's cost `None`.

**Savings are measured, then projected.** The comparison's `savings` holds
what the winner saves per run on the benchmark: the difference in dollars
and seconds, and each as a percentage of the baseline's. A negative saving
is a cost, said as one. Savings are `None` where either side's figure is.

Its `projection` multiplies the saving per run by the production
invocations of the workflow in the last 30 days, and names that window and
that count. It is a projection, labelled as one, never a measurement: the
benchmark's cases may not resemble production's inputs, and the next 30
days may not resemble the last. With no production invocations it is
`None`.

**Promoting the winner is checked first.** A `Promotability` says whether
the winner can still be rebuilt from the workflow's latest revision with
the models authorized now, as `production.promote` would rebuild it (ADR
0092), and, when it cannot, why, as `candidate_rebuild` would say. It
changes nothing; promoting is still `production.promote(workflow_id,
experiment_id=...)`, the `promote` action. The comparison's `command` is
that promotion's `azathoth workflow promote` command.

## Consequences

- The editor can optimize a workflow against a benchmark, watch each
  candidate as it finishes, stop it between candidates, read every
  experiment, and promote the winner, through the service API alone.
- A person can see what promoting would change and save before promoting,
  in dollars and seconds measured on the benchmark, and how that might add
  up in production, said as a projection.
- The command line and the API cannot disagree about experiments, since
  the command line calls the API.
- A remote in 1.6 decides each of these by the action it is.

## Alternatives Considered

### Comparing against the configured candidate alone

It is always in an experiment's first generation and needs no production.
But promoting replaces what production runs, not what the workflow
configures; when they differ, a comparison against the configured
candidate would say what promoting saves over something production no
longer runs.

### Savings from the scores

The cost and latency scores already rank candidates. They are normalized
against the session's targets and capped, so two sessions with different
targets give the same runs different scores, and neither says a dollar
figure. The case runs hold what each run cost and took, so savings are
measured from them.

### Recording a cancelled session

A session stopped part way has no final evaluation, and its last
generation may have run only some candidates. Ranking that beside complete
experiments would compare candidates that never ran the same cases. The
generations it finished are complete experiments, and are kept.
