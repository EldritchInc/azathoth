# Getting Started

This guide takes one workflow from a JSON file to production. On the way, it
uses every stage of Azathoth's lifecycle:

```text
import ──► run ──► benchmark ──► optimize ──► promote ──► invoke
```

The workflow is `examples/workflows/classify-sentiment.json`, one prompt step
that labels text `positive` or `negative`. It is small and cheap to run, and
it is complete.

Notice what you won't do along the way: write code. A workflow is a document
that composes steps, prompts, model requirements and tools. Azathoth runs it,
measures it against a benchmark, finds cheaper or faster models that still
pass, and deploys only what you deliberately promote. Code belongs in tools,
and this workflow needs none.

Each command is shown for the macOS Terminal and for Windows PowerShell 7.

## Before You Start

You need:

- Azathoth installed in an active venv, with the repository cloned and your
  terminal inside it (see [Installing Azathoth](install.md));
- an OpenRouter key in `OPENROUTER_API_KEY` (see
  [Connecting OpenRouter](openrouter.md)).

Use a database of its own for this guide, so you can delete it afterwards:

```bash
export AZATHOTH_DATABASE="$HOME/azathoth-work/getting-started.db"
```

```powershell
$env:AZATHOTH_DATABASE = "$HOME\azathoth-work\getting-started.db"
```

Then create it:

```bash
azathoth init
```

```powershell
azathoth init
```

`init` creates the database and installs the standard tools, `run_workflow`
and `loop_workflow`. This guide's workflow uses neither, but every database
starts the same way.

## 1. Import the Workflow

```bash
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow list
```

```powershell
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow list
```

Import saves the workflow as revision 1. Importing a changed document later
adds revision 2, and so on. Nothing is ever overwritten, and
`azathoth workflow history` lists every revision.

Look at what you imported:

```bash
azathoth workflow show 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth workflow show 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

The step's prompt has a `{text}` placeholder, filled from the workflow's
input. The step doesn't name a model. It states requirements instead: text in,
text out. Importing and inspecting need no provider key.

## 2. Authorize Models

Azathoth chooses a model for each step from the models you have authorized.
Find a few in OpenRouter's current list and authorize them. Authorize your
everyday default first, because a step uses the first authorized model that
meets its requirements:

```bash
azathoth model list | grep -i <vendor>
azathoth model authorize openrouter/<vendor>/<default-model>
azathoth model authorize openrouter/<vendor>/<cheaper-model>
azathoth model portfolio
```

```powershell
azathoth model list | Select-String -Pattern <vendor>
azathoth model authorize openrouter/<vendor>/<default-model>
azathoth model authorize openrouter/<vendor>/<cheaper-model>
azathoth model portfolio
```

Authorize at least two models. The optimizer in step 5 compares models, so
it needs alternatives, ideally cheaper than your default.

## 3. Run It

```bash
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."' --output text
```

```powershell
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."' --output text
```

The report shows the run's ID and status. For the step, it shows the provider
and model used, the tokens, the latency, the estimated cost and the output,
`positive`. `--output result` prints just the answer instead.

`--input` takes JSON, so a string needs its own double quotes inside the
single quotes.

Every run is saved. List them, or look at one again:

```bash
azathoth workflow runs 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth run show <RUN_ID>
```

```powershell
azathoth workflow runs 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth run show <RUN_ID>
```

## 4. Measure It With a Benchmark

One good answer proves little. A benchmark is a set of cases, each with an
input and an expected outcome, and it says what "correct" means for this
workflow. `examples/benchmarks/classify-sentiment.json` has five cases:

- two **exact** cases, which demand the bare lowercase label;
- two **normalized** cases, which accept any letter case and surrounding
  whitespace;
- one **schema** case, which checks the answer's form rather than its
  judgment.

```bash
azathoth benchmark import examples/benchmarks/classify-sentiment.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth benchmark import examples/benchmarks/classify-sentiment.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

The report shows how many cases passed, with latency and cost.

Benchmarks grow from real use. When a run gets something wrong, mark it bad
and record the correct output. Then `benchmark add-case --from-run` turns it
into a new case, and every future candidate is judged against it:

```bash
azathoth run feedback <RUN_ID> --bad --reason "Sarcasm is negative." --corrected-output '"negative"'
azathoth benchmark add-case 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --from-run <RUN_ID> --comparison exact
```

```powershell
azathoth run feedback <RUN_ID> --bad --reason "Sarcasm is negative." --corrected-output '"negative"'
azathoth benchmark add-case 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --from-run <RUN_ID> --comparison exact
```

`benchmark add-case` also takes `--expected '<JSON>'` to state the expected
value directly instead of taking it from the run's corrected output.

## 5. Optimize It

```bash
azathoth workflow optimize 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --benchmark 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --target-latency 5 --target-cost 0.001
```

```powershell
azathoth workflow optimize 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --benchmark 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --target-latency 5 --target-cost 0.001
```

Optimization runs in generations. Each generation runs every candidate
against every benchmark case, scores them, picks a winner, and then proposes
the next generation's candidates:

1. **Generation 1** runs the workflow as configured. That establishes the
   baseline. From it, the optimizer proposes candidates that each move one
   prompt step to an authorized model that is strictly cheaper and still
   meets the step's requirements.
2. The **final evaluation** runs those cheaper candidates alongside the
   baseline, and picks the best of them.

So the default, one generation, compares models. With `--generations 2` or
more, each further generation tries cheaper models again from the latest
winner, and the final evaluation measures the last round. When the last
generation proposes nothing new, the final evaluation is skipped, and the
report says so.

Candidates are scored on:

- **quality**: how many cases passed;
- **reliability**: how many runs succeeded;
- **latency**, against `--target-latency`, in seconds;
- **cost**, against `--target-cost`, in US dollars per run.

The benchmark defines what correct means, so `optimize` takes no expected
value of its own.

For each generation and for the final evaluation, the report names the
**winner**. It lists every step of the winning candidate, with its step ID
and the model it ran on, then the winner's scores. The report ends with the
winning experiment's ID; that experiment's winner is the one to deploy. The
evidence is saved:

```bash
azathoth workflow experiments 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth experiment show <EXPERIMENT_ID>
```

```powershell
azathoth workflow experiments 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth experiment show <EXPERIMENT_ID>
```

Optimizing never changes production, and it never changes your workflow.
What happens next is your decision.

## 6. Promote It

Promotion turns a workflow into production. It binds every prompt step to one
exact model and records a production revision.

To deploy the optimizer's winner, pass the winning experiment's ID from the
end of the optimize report:

```bash
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --experiment <EXPERIMENT_ID>
azathoth workflow production 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --experiment <EXPERIMENT_ID>
azathoth workflow production 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

The winner is rebuilt from the workflow's current revision and checked against
what the experiment measured, so production runs on exactly the models that
won. Promotion refuses the experiment if it measured a different revision, for
example because you imported a new revision after optimizing, or if a winning
model is no longer authorized.

Optimizing is never required. Without `--experiment`, promotion deploys the
workflow as configured, with each prompt step on the first authorized model
that meets its requirements:

```bash
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

`workflow production` shows what is deployed now, including each prompt
step's primary model. Production keeps running on those models until you
promote again, even if you change the configuration or the portfolio in the
meantime. `workflow revisions` lists every promotion.

### Pin the Winner's Models in the Workflow

To make the winner's models part of the workflow itself, so that a plain
`workflow promote` uses them from now on, pin each prompt step to the model
the winner used for that step, in a new revision.

Export the current revision to a file:

```bash
azathoth workflow export 5e2e0b6a-3c1d-4b7e-9f20-000000000001 > classify-sentiment-pinned.json
```

```powershell
azathoth workflow export 5e2e0b6a-3c1d-4b7e-9f20-000000000001 > classify-sentiment-pinned.json
```

Open the file in a text editor. For each step the winner listed, find that
step's `model_selection`, which currently holds `requirements`:

```json
"model_selection": {
  "requirements": {
    "required_capabilities": [],
    "required_input_modalities": ["text"],
    "...": "..."
  }
}
```

Replace it with the winner's model for that step. Split the model identifier
at its first `/`: `openrouter` is the provider, and the rest is the model:

```json
"model_selection": {
  "provider": "openrouter",
  "model": "<vendor>/<model>"
}
```

Save the file, import it as the next revision, and benchmark it again to
confirm it performs as the winner did:

```bash
azathoth workflow import classify-sentiment-pinned.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth workflow import classify-sentiment-pinned.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

Then promote the new revision without `--experiment`. The experiment measured
the earlier revision, so `--experiment` refuses it now; the benchmark you just
ran is the evidence for the new one. If the winner used the same model your
workflow already runs on, there is nothing to pin.

## 7. Invoke Production

```bash
azathoth workflow invoke 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"The checkout flow was painless."' --output result
```

```powershell
azathoth workflow invoke 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"The checkout flow was painless."' --output result
```

It prints `{"result": "positive"}`.

`run` and `invoke` differ in what they execute:

- `workflow run` executes the configuration as it is now. Use it while you
  build and test.
- `workflow invoke` executes what was promoted. Callers, other workflows
  included, use invoke.

Every invocation is recorded, with a link to the run it produced:

```bash
azathoth workflow invocations 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth invocation show <INVOCATION_ID>
```

```powershell
azathoth workflow invocations 5e2e0b6a-3c1d-4b7e-9f20-000000000001
azathoth invocation show <INVOCATION_ID>
```

## 8. Clean Up

Everything this guide created lives in its database. Delete it, and remove
the pinned document if you made one:

```bash
rm -f "$AZATHOTH_DATABASE" classify-sentiment-pinned.json
unset AZATHOTH_DATABASE
```

```powershell
Remove-Item $env:AZATHOTH_DATABASE, classify-sentiment-pinned.json -ErrorAction SilentlyContinue
Remove-Item Env:AZATHOTH_DATABASE
```

## Where to Go Next

- [Examples Tour](examples.md): child workflows, loops, routing, a workflow
  that writes workflows, concurrent code review, and a novel.
- [Concepts](concepts.md): how Azathoth is put together, and why.
- [CLI reference](../src/azathoth/cli/README.md): every command and its
  output.
- [Architecture decisions](adrs/README.md): why Azathoth works the way it
  does.
