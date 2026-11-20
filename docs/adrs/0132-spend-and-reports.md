# ADR 0132: Spend and Reports

- Status: Accepted
- Date: 2026-11-19

## Context

Every model call Azathoth makes records what it cost, as
`estimated_cost_usd` on its step's metrics (ADR 0030), and a run's cost is
the sum of its steps' (ADR 0117). Benchmark executions and experiments
record what their judges cost apart from the runs they judged (ADRs 0130
and 0131). Nothing adds any of it up. A person who wants to know what an
instance spent last month, on which workflow or model, reads runs one at a
time.

The one figure is also two kinds of number under one name. OpenRouter
reports what it charged for each call, as `usage.cost`, and Azathoth keeps
that; it is a bill. Bedrock reports tokens, and Azathoth multiplies them by
the price its operator configured (ADR 0103); that is an estimate, as good
as the price. A model nobody priced records `None`, and unknown is never
free. A report that adds the three together without saying so would read
as a bill it is not.

A step that starts child runs records its own call's cost with each
child's added in (ADR 0117), so a run's cost is what it caused. Adding
every kept run's cost would count each child twice, and would put a
child's dollars on the parent step's model.

Periods are a person's: "yesterday" in New York is not yesterday in UTC,
and a day that a clock moves through is 23 or 25 hours long. ADR 0127
reserves the `read_spend` action, and `/v1/spend` on a remote, for the
spend and reports 1.5 adds.

## Decision

### Every cost says how it is known

A model call records a `cost_basis` beside its cost:

| Basis | When |
| --- | --- |
| `billed` | The provider reported what it charged: OpenRouter's `usage.cost`, and the deterministic provider's nothing |
| `estimated` | Azathoth computed it from a configured price: Bedrock |
| `None` | The call has no cost: an unpriced model |

`ModelResponse` and `StrategyExecutionMetrics` carry it, through the run
journal and storage, and a judge's call carries it as the call it is.
Calls recorded before 1.5 have none, and read their basis from their
provider: OpenRouter's were billed, Bedrock's estimated. The database
schema does not change, since metrics are stored as their JSON.

### Each call is counted once

Spend is a ledger of calls. Each entry has when the call ended, the
workflow and run it belongs to, its model and provider, its source, its
basis, and its cost or that it was unpriced:

| Source | What |
| --- | --- |
| `run` | A step of a kept run, a benchmark's or an experiment's case runs among them |
| `production` | A step of a production invocation's run |
| `judging` | Each call a judge made judging a kept run, as the run's evaluation records it, on that run's workflow |

A step that started child runs is entered at its own cost, the children's
taken back out, and each child run is entered for itself. So every dollar
is counted once, on the model that spent it. A tool's step calls no model,
so only its children are entered. A run that failed is counted for the
steps it executed. A run that never finished, interrupted or cancelled, is
not yet kept, and is counted once it is resumed and finishes. A judge's
call that raised before replying recorded no usage, so nothing is known of
it, and it is left out, as a benchmark's judge cost leaves it.

### Spend is grouped into periods in a time zone

A report covers `since` to `until`, grouped by `day`, `week` or `month`,
in an IANA time zone, and by one of `workflow`, `model`, `provider` or
`source`. Periods are computed in that zone with `zoneinfo`, so a day a
clock moves through is as long as it was. A week is an ISO week, starting
on Monday. Every period in the range is listed, spent in or not, so a
chart or a spreadsheet has no gaps; the first and last periods are cut to
the range, and say so by their start and end.

Each row has its period's start and end, with their offsets, its group,
the billed dollars, the estimated dollars, how many calls it holds and how
many of them were unpriced. The report totals each column. Billed and
estimated are never added into one figure.

The API's time zone is UTC unless one is named; the command line's is the
computer's own. An unknown time zone, a `since` after its `until`, or a
grouping or period not listed, is `invalid_argument`.

### Reading spend

| Call | Returns | Action |
| --- | --- | --- |
| `spend.report(*, since, until, period="day", group="workflow", time_zone="UTC", workflow_id=None)` | A `SpendReport` | `read_spend` |

`azathoth spend` prints it, with `--since`, `--until`, `--by`, `--group`,
`--time-zone` and `--workflow`, as text, as JSON with `--format json`, or
as CSV with `--format csv`. A CSV report is RFC 4180, with a header row;
its times are ISO 8601 with their offsets and its amounts unrounded, so a
spreadsheet adds them exactly. `--output` writes it to a file.

The call is the command's: the command line is a thin wrapper over it, as
every 1.5 command that reads is. Serving it at `/v1/spend` on a remote
comes with the rest of ADR 0127, in 1.6; a remote's spend will be only
what ran there.

## Consequences

- A person can see what an instance spent, in any period, in their own
  time zone, by workflow, model, provider or source, and take it to a
  spreadsheet.
- A billed dollar and an estimated one are never mistaken for each other,
  and an unpriced call is counted, never taken for free.
- A child run's cost is counted once, on its own model, so a report by
  model says which model spent it.
- The editor's spend and report pages read the same call.

## Alternatives Considered

### Summing each run's cost

A run's cost already holds its children's, so summing runs is simple, and
right for one run. Across runs it counts every child twice, and by model
it puts the children's dollars on the parent's.

### Asking the providers for the bill

OpenRouter and AWS each keep an account of what was charged. Asking them
needs credentials beyond a model key, describes an account rather than an
instance, and cannot say which workflow spent it. The calls already record
what each cost, and say how it is known.

### Buckets in UTC alone

UTC needs no time zone and no daylight saving. But a person's day, week
and month are in their own zone, and a report in UTC puts an evening's
spend on the next day.
