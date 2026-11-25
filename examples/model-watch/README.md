# Model Watch Example

AI labs keep shipping models. `model-watch.json` keeps up while you sleep.
Each night it finds the models released since its last run, approves them on
your machine only, tries them on your own workflows and benchmarks, and, when
one does the same work for less, leaves a proposal waiting for you. It never
promotes anything. You do, when you choose.

```text
Discover New Models ──► Add to Local Portfolio ──► Benchmark Against New Models
                                                              │
                     Propose Winner ◄── Compare Cost & Quality ◄┘
```

| Step | What it does | What it says |
| --- | --- | --- |
| Discover New Models | Lists the models providers serve now that the ledger has never held | `3 new models since 2026-11-24T03:00:00+00:00.` |
| Add to Local Portfolio | Authorizes them in this machine's portfolio, and nowhere else | `Approved 3 models on this machine for testing. Production stays locked.` |
| Benchmark Against New Models | Optimizes each target's workflow on its own benchmark | `Tested 3 new models on 2 workflows' own cases. Not a leaderboard.` |
| Compare Cost & Quality | Sets each winner beside what it would replace | `Same accuracy. 62% cheaper.` |
| Propose Winner | Proposes each winner on a new model, and records every new model | `Waiting for a human: 1 proposal.` |

Each step is a process tool, and each emits what it says, so the editor shows
it as the step finishes.

| Document | ID |
| --- | --- |
| `workflows/model-watch.json` | `d7000000-0000-4000-8000-000000000020` |
| `tools/discover-new-models.json` | `d7000000-0000-4000-8000-000000000001` |
| `tools/add-to-local-portfolio.json` | `d7000000-0000-4000-8000-000000000002` |
| `tools/benchmark-against-new-models.json` | `d7000000-0000-4000-8000-000000000003` |
| `tools/compare-cost-and-quality.json` | `d7000000-0000-4000-8000-000000000004` |
| `tools/propose-winner.json` | `d7000000-0000-4000-8000-000000000005` |
| `watch.json` | the demo watch: two targets of the ticket-triage example |

## The Watch

The workflow's input is the watch: which workflows to try new models on, and
where the ledger is kept.

```json
{
  "ledger": "~/.azathoth/model-watch-ledger.json",
  "limit": 5,
  "modalities": ["text"],
  "targets": [
    {
      "workflow": "f1000000-0000-4000-8000-000000000010",
      "benchmark": "f1000000-0000-4000-8000-000000000050",
      "target_latency": 5,
      "target_cost": 0.01
    },
    {
      "workflow": "f1000000-0000-4000-8000-000000000030",
      "benchmark": "f1000000-0000-4000-8000-000000000060",
      "target_latency": 30,
      "target_cost": 0.05
    }
  ]
}
```

- `targets`: each workflow to try new models on, the benchmark of its own
  cases to try them on, and the latency in seconds and cost in US dollars it
  is scored against, as `workflow optimize` takes them. `generations` is 1
  unless a target names more. Name each workflow once.
- `ledger`: the file the watch keeps its memory in.
- `limit`: how many new models to try a night, 5 unless named. The rest wait
  for the next night.
- `providers`: only these providers' models, when named.
- `modalities`: only models whose input and output take every one of these,
  `text` unless named.

A watch with no target, a target without both IDs or both limits, a
workflow named twice, or a workflow or benchmark this instance does not hold
fails the first step, before anything is authorized.

## The Ledger

The ledger holds every model the watch has ever considered, with when, and
what became of it:

```json
{
  "version": 1,
  "checked_at": "2026-11-25T03:00:00+00:00",
  "models": {
    "openrouter/acme/fast-2": {"seen": "2026-11-25T03:00:00+00:00", "status": "proposed", "won": ["f1000000-0000-4000-8000-000000000010"]},
    "openrouter/acme/big-3": {"seen": "2026-11-25T03:00:00+00:00", "status": "rejected"},
    "openrouter/other/old-1": {"seen": "2026-11-24T03:00:00+00:00", "status": "baseline"}
  }
}
```

- A model is new when a provider serves it and the ledger does not hold it.
  A model rejected a week ago is still in the ledger, so it never comes back.
- The first night records every model served as the `baseline` and tries
  none, so the watch starts from what exists that night.
- A model is `proposed` when it won a target, and `rejected` when it won none.
- To try a model again, delete its line from the ledger.
- If a target could not be tried one night, the models that won nothing are
  not recorded, so the next night tries them again.

## Running It

With a provider configured and models authorized (see the CLI README),
import the ticket-triage workflows and benchmarks the demo watch names, then
the watch itself:

```bash
azathoth tool import examples/ticket-triage/tools/finalize-triage.json
azathoth workflow import examples/ticket-triage/workflows/classify-ticket.json
azathoth workflow import examples/ticket-triage/workflows/triage-ticket.json
azathoth benchmark import examples/ticket-triage/benchmarks/classify-ticket.json
azathoth benchmark import examples/ticket-triage/benchmarks/triage-ticket.json

for tool in examples/model-watch/tools/*.json; do
    azathoth tool import "$tool"
done

azathoth workflow import examples/model-watch/workflows/model-watch.json
```

Copy the demo watch, point its targets at your own workflows and benchmarks,
and run it once. The first run only records the baseline:

```bash
mkdir -p ~/.azathoth
cp examples/model-watch/watch.json ~/.azathoth/watch.json

azathoth workflow run d7000000-0000-4000-8000-000000000020 \
    --input-file ~/.azathoth/watch.json \
    --output result
```

The result is the night's report: each proposal, what was rejected, and
what every step said.

```json
{
  "proposals": [
    {
      "workflow": "f1000000-0000-4000-8000-000000000010",
      "experiment": "<EXPERIMENT_ID>",
      "new_models_used": ["openrouter/acme/fast-2"],
      "cost_percent": 62.4,
      "command": "azathoth workflow promote f1000000-0000-4000-8000-000000000010 --experiment <EXPERIMENT_ID>"
    }
  ],
  "rejected": ["openrouter/acme/big-3"],
  "kept_authorized": [],
  "message": "Waiting for a human: 1 proposal. 1 new model rejected.",
  "summary": [
    "2 new models since 2026-11-24T03:00:00+00:00.",
    "Approved 2 models on this machine for testing. Production stays locked.",
    "Tested 2 new models on 2 workflows' own cases. Not a leaderboard.",
    "Same accuracy. 62% cheaper.",
    "Waiting for a human: 1 proposal. 1 new model rejected."
  ]
}
```

## Every Night

Run it from cron, with the venv Azathoth is installed in and the variables
its providers need. The tools run `python`, so the venv must be active:

```bash
# crontab -e
0 3 * * * . "$HOME/azathoth-work/model-watch.env" && azathoth workflow run d7000000-0000-4000-8000-000000000020 --input-file "$HOME/.azathoth/watch.json" --output result >> "$HOME/.azathoth/model-watch.log" 2>&1
```

`model-watch.env` activates the venv and exports `AZATHOTH_DATABASE`,
`AZATHOTH_AUTHOR` and the provider's key, such as `OPENROUTER_API_KEY`. On
Windows, a Task Scheduler task runs the same command from PowerShell.

The tools are given only the variables they declare (ADR 0099):
`AZATHOTH_DATABASE`, `AZATHOTH_AUTHOR`, `OPENROUTER_API_KEY`, and Bedrock's
`AZATHOTH_BEDROCK`, `AZATHOTH_BEDROCK_PRICING` and `AWS_*`.

## Promoting a Winner

In the morning, look at a proposal before promoting it:

```bash
azathoth experiment compare <EXPERIMENT_ID>
azathoth workflow promote f1000000-0000-4000-8000-000000000010 --experiment <EXPERIMENT_ID>
```

Or open the workflow in the editor and click Promote. Promoting rebuilds the
winner from the models authorized now, so a proposed model stays authorized
on this machine until you promote it or take it away with `azathoth model
deauthorize`. To put the promoted workflow on your team's remote, push it as
you push any workflow.

## What It Never Does

- It never promotes. Optimizing proposes; a person promotes (ADR 0092).
- It never touches a remote or production. It authorizes models only in the
  portfolio of the instance `AZATHOTH_DATABASE` names, and takes back only
  the ones it added and rejected.
- It never tries a model it has already considered.

## Limits

- `workflow optimize` tries cheaper substitutes for each step's model. A new
  model that costs more than the one a step runs on is recorded and
  reported, but not benchmarked.
- A target's benchmark is the judge of "the same accuracy": a winner holds its
  quality when it passes at least as many of the benchmark's cases as what
  runs now. Make the cases worth trusting.
- The Benchmark step may take up to an hour; every other step, two minutes.
