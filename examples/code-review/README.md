# Code Review Example

`review-change.json` reviews a code change with three reviewers at once, for
security, correctness and readability, then merges their findings into one
verdict and has a lead reviewer write the comment.

```text
security reviewer    ─┐
correctness reviewer ─┼─► merge ──► findings? ──► lead reviewer ──► finalize
readability reviewer ─┘                    └───────────────────────►─┘
```

| Document | ID |
| --- | --- |
| `workflows/review-change.json` | `d2000000-0000-4000-8000-000000000010` |
| `tools/merge-reviews.json` | `d2000000-0000-4000-8000-000000000001` |
| `tools/finalize-review.json` | `d2000000-0000-4000-8000-000000000002` |
| `benchmarks/review-change.json` | `d2000000-0000-4000-8000-000000000030` |

## Concurrent Reviewers

The three reviewers depend on nothing but the change, so they share the first
dependency layer and run concurrently. Each reviewer is told to stay in its
own area and to reply in JSON:

```json
{"findings": [{"severity": "high", "file": "app/orders.py", "line": 41, "summary": "...", "suggestion": "..."}]}
```

Each reviewer is its own prompt step with its own model requirements, so each
can be optimized separately. A reviewer whose work is easy can move to a
cheaper model without touching the others.

## Merging

`merge_reviews` is a Python tool, so the verdict is decided by code rather
than by a model:

- each finding is tagged with the reviewers who raised it;
- a finding more than one reviewer raised, with the same file, line and
  summary, ignoring case and surrounding spaces, appears once, tagged with
  all of them;
- findings are ordered high, medium, low, then by file and line;
- the verdict is `request_changes` when any finding is high, `comment` when
  there are any findings, and `approve` when there are none.

## The Lead Reviewer

The lead reviewer writes the comment for the change's author, from the
change and the merged review. It runs only when there are findings. The merge
tool also produces `summary`, `"No issues found."`, and `finalize` reads
`summary` by name, so a clean change gets that summary without a model call
(ADR 0080).

## Running It

With a provider configured and models authorized (see the CLI README):

```bash
azathoth tool import examples/code-review/tools/merge-reviews.json
azathoth tool import examples/code-review/tools/finalize-review.json

azathoth workflow import examples/code-review/workflows/review-change.json

azathoth workflow run d2000000-0000-4000-8000-000000000010 \
    --input '{"title": "Rename total to order_total", "description": "A clearer name; no behavior changes.", "diff": "-def total(order):\n+def order_total(order):\n"}' \
    --output result
```

The input is the change's title, description and unified diff. The result
is the review:

```json
{
  "verdict": "approve",
  "findings": [],
  "counts": {"high": 0, "medium": 0, "low": 0},
  "summary": "No issues found."
}
```

## Benchmark

`benchmarks/review-change.json` has four cases:

- a schema case requiring that a change with a SQL injection is blocked by a
  high-severity security finding;
- a schema case requiring that a pure rename is approved with no findings;
- two semantic cases, judging whether the review names the real problem: the
  SQL injection, and an off-by-one error in pagination.

Schema cases need no judge; semantic cases do:

```bash
azathoth judge add <MODEL_IDENTIFIER>
azathoth benchmark import examples/code-review/benchmarks/review-change.json
```
