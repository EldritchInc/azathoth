# Novel Example

`write-novel.json` writes a novel from an idea. It plans the story, outlines
up to 18 chapters, and writes them one at a time, each through its own
editing loop, until the story ends. Then it gives the whole book one last
editorial review and edit pass, checks it for coherence, and assembles it.

It is built from four workflows that loop over each other with the
`loop_workflow` tool (ADR 0090):

```text
write-novel
├── chapter loop ──────► write-chapter          one iteration per chapter
│                        └── revision loop ──► revise-chapter
└── final-edits loop ──► edit-queue             one iteration per chapter to change
                         └── revision loop ──► revise-chapter
```

| Workflow | ID | One run |
| --- | --- | --- |
| `write-novel.json` | `e1000000-0000-4000-8000-000000000070` | The whole novel |
| `write-chapter.json` | `e1000000-0000-4000-8000-000000000040` | Draft, review, revise and note one chapter |
| `edit-queue.json` | `e1000000-0000-4000-8000-000000000060` | Apply the final review's requests to one chapter |
| `revise-chapter.json` | `e1000000-0000-4000-8000-000000000010` | Apply editorial requests once, then check which are still unmet |

## The Editing Loop

After each chapter is drafted, an editor reviews it and lists requests. When
there are any, the revision loop runs `revise-chapter` until a second editor
finds every request satisfied, or three passes have been made:

```text
apply requests ──► verify ──► unmet requests? ──► yes: next pass, on the unmet requests only
                                              └─► no:  done
```

Then the chapter's continuity notes are updated for the chapters still to
come. The notes step also says whether the story is complete, and the chapter
loop stops there even if the outline planned more chapters. Chapters past the
ending are never written.

## Running It

The book needs language models. With a provider configured and models
authorized (see the CLI README), import the loop tool and the novel's own
tools and workflows:

```bash
azathoth tool import examples/tools/loop-workflow.json

for file in examples/novel/tools/*.json; do azathoth tool import "$file"; done
for file in examples/novel/workflows/*.json; do azathoth workflow import "$file"; done
```

In PowerShell:

```powershell
azathoth tool import examples/tools/loop-workflow.json

Get-ChildItem examples/novel/tools/*.json | ForEach-Object { azathoth tool import $_.FullName }
Get-ChildItem examples/novel/workflows/*.json | ForEach-Object { azathoth workflow import $_.FullName }
```

The loop invokes its children, so the three loop bodies must be promoted:

```bash
azathoth workflow promote e1000000-0000-4000-8000-000000000010
azathoth workflow promote e1000000-0000-4000-8000-000000000040
azathoth workflow promote e1000000-0000-4000-8000-000000000060
```

Then write a short book:

```bash
azathoth workflow run e1000000-0000-4000-8000-000000000070 \
    --input '{"idea": "A lighthouse keeper discovers the light keeps the sea asleep.", "max_chapters": 3}' \
    --output result
```

The result is the novel:

```json
{"title": "...", "chapters": [{"number": 1, "title": "...", "text": "..."}], "markdown": "# ...", "report": "..."}
```

`markdown` is the whole book, and `report` is the coherence check's verdict.

## The Request

Only `idea` is required:

| Field | Default | Meaning |
| --- | --- | --- |
| `idea` | | What the novel is about, in any detail |
| `max_chapters` | 18 | The most chapters to plan, never more than 18 |
| `max_revisions` | 3 | The most revision passes per chapter or final edit |
| `chapter_timeout_seconds` | 1800 | How long one chapter may take |
| `chapter_budget_seconds` | chapters × chapter timeout | How long the whole chapter loop may take |
| `edit_timeout_seconds` | 1800 | How long one final edit may take |
| `edit_budget_seconds` | edits × edit timeout | How long the whole final-edits loop may take |
| `chapter_workflow_id` | `e1…0040` | The chapter loop's body |
| `revision_workflow_id` | `e1…0010` | The revision loop's body |
| `edit_queue_workflow_id` | `e1…0060` | The final-edits loop's body |

Each loop's child ID is a constant input in the workflow that runs the loop
(ADR 0094), passed to the tool that prepares the loop's settings:

```json
{"name": "chapter_workflow_id", "source": {"value": "e1000000-0000-4000-8000-000000000040"}}
```

| Workflow | Tool | Constant input |
| --- | --- | --- |
| `write-novel` | `prepare-chapters` | `chapter_workflow_id` |
| `write-novel` | `prepare-final-edits` | `edit_queue_workflow_id` |
| `write-chapter` | `prepare-revision` | `revision_workflow_id` |
| `edit-queue` | `pick-edit` | `revision_workflow_id` |

The request can override any of them for one run, for example to try a
different chapter workflow. To change the default, change the constant and
import the workflow again; no tool changes.

## Steps That Run Only Sometimes

The revision loop runs only when the editor asked for changes, and the
final-edits loop only when the final review did. Each is a conditioned step,
and the tool that prepares it also produces the value to use when it is
skipped:

```text
revise   (loop, runs when needs_revision)   ──► chapter, when it ran
prepare  (tool)                             ──► chapter, the draft as it is
```

The steps that follow read `chapter` by name. The first step in declared
order that produced it wins (ADR 0080), so `revise` is declared before
`prepare`, even though it depends on it. When it ran, its revision wins; when
it was skipped, the unrevised draft is used.

## Time

Each loop runs inside one tool call, and its settings say how long it may
take (ADR 0093). The chapter loop's budget is the number of chapters times
the chapter timeout, 30 minutes each, so a full 18-chapter book may take up
to 9 hours. Each final edit, including its revision loop, gets its own 30
minutes, and the final-edits loop's budget covers every queued edit. Both
budgets are capped just under the loop tool's 24-hour timeout.

A loop that runs out of time fails, and so does the novel:

```text
Tool implementation c1000000-0000-4000-8000-000000000022 exited with status 1: Loop over child workflow e1000000-0000-4000-8000-000000000040 ran out of time after 4 iterations.
```

To give chapters or edits more time, set `chapter_timeout_seconds` or
`edit_timeout_seconds` in the request; the budgets follow. To bound a whole
loop directly, set `chapter_budget_seconds` or `edit_budget_seconds`. No tool
document needs to change.

## Models

The final review and the coherence check read the whole book at once, so
they require a model with at least a 200,000-token context window. Every
other step requires text in and text out.

## Storage

Every iteration of every loop is its own production invocation, with its own
run. A run records each step's inputs and outputs, prompts and replies
included. An 18-chapter novel can record up to about 150 runs: one per
chapter and per final edit, plus one per revision pass of each.

The final-edits loop carries the whole book in its state, so each of its
invocations records the whole book again. The database grows with the length
of the book times the number of chapters the final review asks to change.

## Benchmark

`benchmarks/revise-chapter.json` holds two semantic cases for the inner
editing loop's body: the revision should satisfy every request, say it is
done, and keep the chapter's events. Semantic cases are judged, so add a judge first:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth benchmark import examples/novel/benchmarks/revise-chapter.json
```
