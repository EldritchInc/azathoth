# Examples Tour

The `examples/` folder holds complete, importable workflows. They are
ordered here from the smallest to the largest. Each example adds one idea to
the ones before it, so working through them in order teaches most of
Azathoth.

Every example is a set of JSON documents: workflows, tools and benchmarks.
You build a workflow by composing steps, prompts, model requirements, tools
and other workflows. You don't program it. Code appears in only one place:
inside tools, which do the deterministic work, such as counting, merging or
validating. That split is the point. Workflows can be built, reviewed and
improved by platform and domain teams, and engineering effort goes into
tools.

Each example's own README explains its design in depth. This guide gives you
the order to run things in.

## Before You Start

You need:

- Azathoth installed in an active venv (see [Installing Azathoth](install.md));
- the repository cloned, with your terminal inside it (see
  [Get the Examples](install.md#6-get-the-examples)).

Examples 1, 3 and 4 need nothing else. The others call language models, so
they need an OpenRouter key and at least one authorized model (see
[Connecting OpenRouter](openrouter.md)). Their benchmarks with semantic
cases also need a judge.

To keep the examples apart from your own work, give them a database of their
own:

```bash
export AZATHOTH_DATABASE="$HOME/azathoth-work/examples.db"
```

```powershell
$env:AZATHOTH_DATABASE = "$HOME\azathoth-work\examples.db"
```

Then create it and install the standard tools:

```bash
azathoth init
```

```powershell
azathoth init
```

Examples 3, 4 and 8 compose workflows with `run_workflow` and
`loop_workflow`, which ship with Azathoth. Each of them runs
`azathoth tool install-standard` too, which is safe to repeat: a tool that is
already installed is left alone.

Importing a document twice is harmless. Azathoth keeps both as revisions, and
an identical import is marked as such. So each example below imports
everything it needs, even when an earlier example already did.

## At a Glance

| # | Example | What it shows | Models | Promote first | Judge for its benchmark |
| --- | --- | --- | --- | --- | --- |
| 1 | Word count | Tools, redundancy, benchmarks from corrected runs | No | No | No |
| 2 | Classify sentiment | The whole lifecycle: run, benchmark, optimize, promote, invoke | Yes | No | Only for the semantic benchmark |
| 3 | Child workflow | One workflow calling another | No | The child | — |
| 4 | Countdown loop | Repeating a child workflow | No | The loop body | — |
| 5 | Ticket triage | Conditional routing, a cheaper classifier | Yes | No | Only for the triage benchmark |
| 6 | Workflow writer | JSON replies, a validator tool, one repair pass | Yes | No | Yes |
| 7 | Code review | Concurrent reviewers, a merge done by code | Yes | No | Yes |
| 8 | Novel | Nested loops, conditional revision, long runs | Yes, including a 200,000-token context window | Three loop bodies | Yes |

`workflow run` runs the workflow as it is configured right now.
`workflow invoke` runs what was promoted to production. A workflow that calls
another workflow always invokes it, so the child must be promoted first.

## 1. Word Count: Tools Without Models

`redundant-word-count.json` counts words twice in one step layer: once with a
process tool and once with a Python tool. If one of them fails, the other's
count is still the answer.

```bash
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
```

```powershell
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
```

It prints `8`.

A tool can carry test cases. Verify the process tool against its own:

```bash
azathoth tool verify 55555555-5555-5555-5555-555555555555 --version 1.0.0
```

```powershell
azathoth tool verify 55555555-5555-5555-5555-555555555555 --version 1.0.0
```

`word-count-messages.json` is the same workflow, but each step announces
itself as it starts. A benchmark is a set of cases with expected outcomes.
Run the word-count benchmark against this workflow:

```bash
azathoth workflow import examples/workflows/word-count-messages.json
azathoth benchmark import examples/benchmarks/word-count.json
azathoth benchmark run b1000000-0000-4000-8000-000000000001 --workflow a1000000-0000-4000-8000-000000000002
```

```powershell
azathoth workflow import examples/workflows/word-count-messages.json
azathoth benchmark import examples/benchmarks/word-count.json
azathoth benchmark run b1000000-0000-4000-8000-000000000001 --workflow a1000000-0000-4000-8000-000000000002
```

The CLI reference shows how to turn a wrong answer into a new benchmark case.
Feedback on a run marks it bad and records the correct output, and
`benchmark add-case --from-run` captures it. See
[Capturing a Corrected Run as a Case](../src/azathoth/cli/README.md#capturing-a-corrected-run-as-a-case).

## 2. Classify Sentiment: The Whole Lifecycle

`classify-sentiment.json` is one prompt step that labels text `positive` or
`negative`. It is small enough to take through every stage.

Import it and run it once:

```bash
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."' --output result
```

```powershell
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."' --output result
```

Measure it against a benchmark of five cases, with exact, normalized and
schema comparisons:

```bash
azathoth benchmark import examples/benchmarks/classify-sentiment.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth benchmark import examples/benchmarks/classify-sentiment.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

Optimize it. The first generation measures the workflow as configured, and
proposes cheaper candidates: each authorized model that is cheaper than the
current one and meets the step's requirements. A final evaluation then runs
them alongside the original, so the default of one generation compares
models. Candidates are ranked on quality, latency (seconds) and cost (US
dollars), against the targets you give. It needs at least two authorized models to have anything
to compare.

```bash
azathoth workflow optimize 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --benchmark 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --target-latency 5 --target-cost 0.001
azathoth workflow experiments 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth workflow optimize 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --benchmark 5e2e0b6a-3c1d-4b7e-9f21-000000000000 --target-latency 5 --target-cost 0.001
azathoth workflow experiments 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

The report names the winner and the model each of its steps ran on, and ends
with the ID of the experiment that chose it.
Optimizing records evidence, and it never changes your workflow or
production. Promotion is a separate, deliberate step. Promote the winner by
its experiment ID, then invoke production:

```bash
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --experiment <EXPERIMENT_ID>
azathoth workflow invoke 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"The checkout flow was painless."' --output result
```

```powershell
azathoth workflow promote 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --experiment <EXPERIMENT_ID>
azathoth workflow invoke 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"The checkout flow was painless."' --output result
```

It prints `{"result": "positive"}`. Without `--experiment`, promotion deploys
the workflow as configured; see
[Promote It](getting-started.md#6-promote-it).

`examples/benchmarks/classify-sentiment-semantic.json` judges the same
workflow by meaning rather than by exact label. With a judge added (see
[Add Judges](openrouter.md#5-add-judges)):

```bash
azathoth benchmark import examples/benchmarks/classify-sentiment-semantic.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f22-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

```powershell
azathoth benchmark import examples/benchmarks/classify-sentiment-semantic.json
azathoth benchmark run 5e2e0b6a-3c1d-4b7e-9f22-000000000000 --workflow 5e2e0b6a-3c1d-4b7e-9f20-000000000001
```

## 3. A Child Workflow

`count-words-in-child.json` has a single step: the `run_workflow` tool, which
invokes another workflow and returns its result. Here the child is the word
count with messages. The child is invoked, so it must be promoted first.
`run_workflow` ships with Azathoth in its standard tool library, which
`tool install-standard` imports.

```bash
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth tool install-standard
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow import examples/workflows/count-words-in-child.json
azathoth workflow promote a1000000-0000-4000-8000-000000000002
azathoth workflow run a1000000-0000-4000-8000-000000000003 --input '{"workflow_id": "a1000000-0000-4000-8000-000000000002", "input": "the old ones wait"}' --output result
```

```powershell
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth tool install-standard
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow import examples/workflows/count-words-in-child.json
azathoth workflow promote a1000000-0000-4000-8000-000000000002
azathoth workflow run a1000000-0000-4000-8000-000000000003 --input '{"workflow_id": "a1000000-0000-4000-8000-000000000002", "input": "the old ones wait"}' --output result
```

It prints `4`.

The child runs as a separate process, started with the `python` on your
`PATH`. That is why the venv has to be active rather than installed with
`pipx`. Nesting is limited to 8 levels.

## 4. A Loop

A workflow is a graph, so no step runs twice in one run. To repeat work, the
`loop_workflow` tool invokes a child workflow once per iteration and passes
each iteration's state to the next. `countdown.json` is the smallest
possible loop body: it counts its state down by one and is done at zero.
`loop-countdown.json` binds the loop's settings, the child and an iteration
limit of 10, as a constant in the document, so the caller supplies only the
starting state.

```bash
azathoth tool import examples/tools/countdown-step.json
azathoth tool install-standard
azathoth workflow import examples/workflows/countdown.json
azathoth workflow import examples/workflows/loop-countdown.json
azathoth workflow promote a1000000-0000-4000-8000-000000000004
azathoth workflow run a1000000-0000-4000-8000-000000000005 --input '{"remaining": 3}' --output result
```

```powershell
azathoth tool import examples/tools/countdown-step.json
azathoth tool install-standard
azathoth workflow import examples/workflows/countdown.json
azathoth workflow import examples/workflows/loop-countdown.json
azathoth workflow promote a1000000-0000-4000-8000-000000000004
azathoth workflow run a1000000-0000-4000-8000-000000000005 --input '{"remaining": 3}' --output result
```

It prints `[3, 2, 1]`. With `"max_iterations": 2` in the document's settings,
the loop stops early with `[3, 2]`.

A loop is bounded three ways:

- its `max_iterations`;
- its time budget, `budget_seconds`: about 2 hours by default, and up to just
  under the tool's 24-hour timeout when the settings ask for more. Each child
  is stopped after `child_timeout_seconds`, 600 by default;
- the same 8-level nesting limit as `run_workflow`.

Every iteration is its own production invocation, so it can be inspected on
its own.

## 5. Ticket Triage: Routing

`triage-ticket.json` classifies a support ticket and sends it to one of four
specialists, chosen by conditions on the category. Then it checks the reply
against support policy and decides whether a person must review it.

```bash
azathoth tool import examples/ticket-triage/tools/finalize-triage.json
azathoth workflow import examples/ticket-triage/workflows/classify-ticket.json
azathoth workflow import examples/ticket-triage/workflows/triage-ticket.json
azathoth workflow run f1000000-0000-4000-8000-000000000030 --input '{"subject": "Charged twice", "body": "My card was charged twice for the March invoice.", "customer_tier": "standard"}' --output result
```

```powershell
azathoth tool import examples/ticket-triage/tools/finalize-triage.json
azathoth workflow import examples/ticket-triage/workflows/classify-ticket.json
azathoth workflow import examples/ticket-triage/workflows/triage-ticket.json
azathoth workflow run f1000000-0000-4000-8000-000000000030 --input '{"subject": "Charged twice", "body": "My card was charged twice for the March invoice.", "customer_tier": "standard"}' --output result
```

The result is a triage record with the category, urgency, reply, and whether
a person must review it.

The classifier also exists on its own, as `classify-ticket.json`. Its
benchmark has six exact cases, so it needs no judge, and classifying a
ticket is a good job for a cheaper model:

```bash
azathoth benchmark import examples/ticket-triage/benchmarks/classify-ticket.json
azathoth workflow optimize f1000000-0000-4000-8000-000000000010 --benchmark f1000000-0000-4000-8000-000000000050 --target-latency 5 --target-cost 0.001
```

```powershell
azathoth benchmark import examples/ticket-triage/benchmarks/classify-ticket.json
azathoth workflow optimize f1000000-0000-4000-8000-000000000010 --benchmark f1000000-0000-4000-8000-000000000050 --target-latency 5 --target-cost 0.001
```

The whole-triage benchmark has semantic cases, so it needs a judge:

```bash
azathoth benchmark import examples/ticket-triage/benchmarks/triage-ticket.json
azathoth benchmark run f1000000-0000-4000-8000-000000000060 --workflow f1000000-0000-4000-8000-000000000030
```

```powershell
azathoth benchmark import examples/ticket-triage/benchmarks/triage-ticket.json
azathoth benchmark run f1000000-0000-4000-8000-000000000060 --workflow f1000000-0000-4000-8000-000000000030
```

More detail: [Ticket Triage Example](../examples/ticket-triage/README.md).

## 6. Workflow Writer: Workflows That Write Workflows

`write-workflow.json` turns a plain-English request into an Azathoth workflow
document. Its prompts reply in JSON. A validator tool checks the draft with
Azathoth's own workflow model, and an invalid draft gets one repair pass.

```bash
azathoth tool import examples/workflow-writer/tools/validate-workflow.json
azathoth tool import examples/workflow-writer/tools/finalize-workflow.json
azathoth workflow import examples/workflow-writer/workflows/write-workflow.json
azathoth workflow run a2000000-0000-4000-8000-000000000010 --input '"Classify a customer review as positive or negative."' --output result > written.json
```

```powershell
azathoth tool import examples/workflow-writer/tools/validate-workflow.json
azathoth tool import examples/workflow-writer/tools/finalize-workflow.json
azathoth workflow import examples/workflow-writer/workflows/write-workflow.json
azathoth workflow run a2000000-0000-4000-8000-000000000010 --input '"Classify a customer review as positive or negative."' --output result > written.json
```

`written.json` says whether the workflow is valid and holds the workflow
itself. A valid one can be pulled out and imported:

```bash
python -c "import json; print(json.dumps(json.load(open('written.json'))['workflow'], indent=2))" > workflow.json
azathoth workflow import workflow.json
```

```powershell
python -c "import json; print(json.dumps(json.load(open('written.json'))['workflow'], indent=2))" > workflow.json
azathoth workflow import workflow.json
```

The validator imports Azathoth, so this example also needs the venv active.

Its benchmark has schema cases and semantic cases, so it needs a judge:

```bash
azathoth benchmark import examples/workflow-writer/benchmarks/write-workflow.json
azathoth benchmark run a2000000-0000-4000-8000-000000000030 --workflow a2000000-0000-4000-8000-000000000010
```

```powershell
azathoth benchmark import examples/workflow-writer/benchmarks/write-workflow.json
azathoth benchmark run a2000000-0000-4000-8000-000000000030 --workflow a2000000-0000-4000-8000-000000000010
```

More detail: [Workflow Writer Example](../examples/workflow-writer/README.md).

## 7. Code Review: Concurrent Reviewers

`review-change.json` reviews a code change with three reviewers at once, for
security, correctness and readability. A Python tool merges their findings
and decides the verdict: code makes that call, not a model. A lead reviewer
writes the comment only when there is something to say.

```bash
azathoth tool import examples/code-review/tools/merge-reviews.json
azathoth tool import examples/code-review/tools/finalize-review.json
azathoth workflow import examples/code-review/workflows/review-change.json
azathoth workflow run d2000000-0000-4000-8000-000000000010 --input '{"title": "Rename total to order_total", "description": "A clearer name; no behavior changes.", "diff": "-def total(order):\n+def order_total(order):\n"}' --output result
```

```powershell
azathoth tool import examples/code-review/tools/merge-reviews.json
azathoth tool import examples/code-review/tools/finalize-review.json
azathoth workflow import examples/code-review/workflows/review-change.json
azathoth workflow run d2000000-0000-4000-8000-000000000010 --input '{"title": "Rename total to order_total", "description": "A clearer name; no behavior changes.", "diff": "-def total(order):\n+def order_total(order):\n"}' --output result
```

A pure rename should come back `approve`, with no findings.

Its benchmark has schema cases and semantic cases, so it needs a judge:

```bash
azathoth benchmark import examples/code-review/benchmarks/review-change.json
azathoth benchmark run d2000000-0000-4000-8000-000000000030 --workflow d2000000-0000-4000-8000-000000000010
```

```powershell
azathoth benchmark import examples/code-review/benchmarks/review-change.json
azathoth benchmark run d2000000-0000-4000-8000-000000000030 --workflow d2000000-0000-4000-8000-000000000010
```

More detail: [Code Review Example](../examples/code-review/README.md).

## 8. Novel: Loops Inside Loops

`write-novel.json` writes a novel from an idea. It plans the story, then
writes the chapters one at a time in a loop. Each chapter has its own editing
loop. A final review and edit pass covers the whole book.

The novel is the most expensive example by far. Start with a short book, and
set a credit limit on your key. It needs an authorized model with a context
window of at least 200,000 tokens, because the final review reads the whole
book at once.

Install the standard tools, which include the loop tool, and import the
novel's tools and workflows:

```bash
azathoth tool install-standard
for file in examples/novel/tools/*.json; do azathoth tool import "$file"; done
for file in examples/novel/workflows/*.json; do azathoth workflow import "$file"; done
```

```powershell
azathoth tool install-standard
Get-ChildItem examples/novel/tools/*.json | ForEach-Object { azathoth tool import $_.FullName }
Get-ChildItem examples/novel/workflows/*.json | ForEach-Object { azathoth workflow import $_.FullName }
```

Promote the three loop bodies (revise, chapter and edit queue), then write a
three-chapter book:

```bash
azathoth workflow promote e1000000-0000-4000-8000-000000000010
azathoth workflow promote e1000000-0000-4000-8000-000000000040
azathoth workflow promote e1000000-0000-4000-8000-000000000060
azathoth workflow run e1000000-0000-4000-8000-000000000070 --input '{"idea": "A lighthouse keeper discovers the light keeps the sea asleep.", "max_chapters": 3}' --output result > novel.json
```

```powershell
azathoth workflow promote e1000000-0000-4000-8000-000000000010
azathoth workflow promote e1000000-0000-4000-8000-000000000040
azathoth workflow promote e1000000-0000-4000-8000-000000000060
azathoth workflow run e1000000-0000-4000-8000-000000000070 --input '{"idea": "A lighthouse keeper discovers the light keeps the sea asleep.", "max_chapters": 3}' --output result > novel.json
```

`novel.json` holds the title, the chapters, the whole book as Markdown, and
the coherence check's verdict. Save the book on its own:

```bash
python -c "import json; print(json.load(open('novel.json'))['markdown'])" > novel.md
```

```powershell
python -c "import json; print(json.load(open('novel.json'))['markdown'])" > novel.md
```

The chapter loop's budget grows with the book: up to 30 minutes for each
chapter, so a full 18-chapter novel needs no changes to any tool. The novel's
README explains that, the request's options, and the inner revision loop's
benchmark: [Novel Example](../examples/novel/README.md).

## Also in `examples/`

- `goals/accurate-answer.json`: a goal document, for `azathoth goal import`.
- `dogfood/exact-match-live.json`: a one-step workflow for checking live
  models on an exact-match task.
- `execute_strategy.py` and `create_optimization_example.py`: small scripts
  that use Azathoth as a Python library rather than through the CLI. Run them
  with `python examples/execute_strategy.py`.

## When Something Fails

`workflow run` reports the step that failed and why. A failure inside a
child or a loop iteration names the child's invocation. Follow it to the run
that failed:

```bash
azathoth invocation show <INVOCATION_ID>
azathoth run show <RUN_ID>
```

```powershell
azathoth invocation show <INVOCATION_ID>
azathoth run show <RUN_ID>
```

The most common causes:

- **The workflow is not deployed to production**: a child or loop body
  wasn't promoted.
- **`No module named azathoth`** from a child, loop or validator: the venv
  isn't active (see [Installing Azathoth](install.md#troubleshooting)).
- **No executable prompt candidate could be generated**: no authorized model
  meets a step's requirements (see
  [Connecting OpenRouter](openrouter.md#troubleshooting)).
