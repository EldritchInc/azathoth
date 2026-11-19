# ADR 0130: Benchmarks Through the Service API

- Status: Accepted
- Date: 2026-11-18

## Context

The service API (ADR 0120) lists a benchmark's revisions, reads one with
its document, and imports a document as its next revision. Everything else
a person does with a benchmark is the command line's alone: `benchmark
cases` and `benchmark case-show` read its cases, `benchmark add-case` adds
one from a recorded run or a file (ADR 0086), `benchmark run` and
`benchmark compare` execute workflows against it (ADR 0040), and
`benchmark executions` and `benchmark execution show` read what they saved
(ADR 0075).

The editor drives Azathoth only through the API, so it can show a
benchmark's document but cannot add a case, turn a run into one, or run a
benchmark. Each command also holds its own logic, beside the calls the API
already makes, so the two could come to disagree.

Nor can any surface create a benchmark except by importing a whole
document, or change or remove a case except by editing and importing one.
ADR 0127's `edit_benchmark` action promises all three: "Create a
benchmark, add and edit its cases, and turn a run into a case".

## Decision

Every call here is an addition to the 1.x service API, on
`instance.benchmarks`. The command line's commands become thin wrappers
over the same calls, as production's and the judges' did (ADRs 0128 and
0129), so there is one implementation of each, and their output is
unchanged. Three new commands give the new calls their command line:
`benchmark create`, `benchmark edit-case` and `benchmark remove-case`. Each
call is one of the 0127 catalog's named actions, for a remote's policy in
1.6.

`benchmark run` and `benchmark compare` are the exception, as `run resume`
is (ADR 0129): they load the runtime from the command line's own provider
discovery and render what they saved as they always have, so they keep
their own reporting, and execute through the same calls `benchmarks.run`
and `benchmarks.compare` make, with the same checks before any case runs.

Every change saves the benchmark's next revision, as importing does (ADR
0076); nothing is changed in place, so every execution still names the
revision it ran, and every earlier revision can still be read.

### Reading cases

| Call | Returns | Action |
| --- | --- | --- |
| `cases(id, revision=None)` | Each case of a revision, in order, the latest by default | `read_catalog` |
| `case(id, case_id, revision=None)` | One case, with its input and expected value | `read_catalog` |

A `BenchmarkCaseSummary` has the case's ID, its comparison, its label, its
description, where it came from (`run`, `file` or `json`) and the run it
came from, if any. A `BenchmarkCaseDetail` adds its input, its expected
value, what its run must cite, and its input's provenance: the content's
digest and media type for a case given a file. A restricted case is the
`read_restricted` action too, as anything restricted is (ADR 0127). A case
the revision does not hold is `not_found`.

### Creating a benchmark, and editing its cases

| Call | Returns | Action |
| --- | --- | --- |
| `create(name, description, *, version="1.0.0")` | A `BenchmarkImport` of revision 1, with no cases | `edit_benchmark` |
| `add_case(id, *, run_id= \| input= \| file=, comparison, expected=, description=, citations=, sensitivity=)` | A `BenchmarkCaseChange`: the case, and the revision it made | `edit_benchmark` |
| `update_case(id, case_id, *, comparison=, expected=, description=, citations=, sensitivity=)` | A `BenchmarkCaseChange` | `edit_benchmark` |
| `remove_case(id, case_id)` | A `BenchmarkCaseChange`: the case removed | `edit_benchmark` |

A new benchmark has a new ID and no cases; it cannot be run until it has
one. `add_case` appends after every case, as `benchmark add-case` does.

**Run to case.** A case from a run replays the input the run received
(ADR 0086). Its expected value is the one given, or else the corrected
output of the run's latest bad judgment (ADR 0129); good feedback never
supplies one, and a run with neither is `invalid_argument`, naming
`expected`. A run given a PDF or an image becomes a case holding its
content's handle, while the content store still holds it; once it does
not, the case is refused as `content_unavailable`. A case from a
restricted run is the `read_restricted` action too.

A case from a file is kept in the content store as a run's file is, and a
case from `input` holds that JSON; either needs an expected value.

**Editing a case** changes what it expects and how it is judged: its
comparison, its expected value, its description, what its run must cite,
and its label. Its ID, its input and where it came from stay, since an
input is what a case was made from. Only what is given changes.

**Labels only go up.** A case is labelled as given, or as its run was; a
case from a run is refused a lower label than the run's (ADR 0123). An
edit may raise a case's label but never lower it, so no edit can call data
less sensitive than it was. Each refusal is `invalid_argument`.

An exact duplicate of another case, with a JSON-equal input, the same
comparison and a JSON-equal expected value, is `conflict`, whether it is
added or made by an edit, and nothing is saved. A case the latest revision
does not hold is `not_found`.

### Executions

| Call | Returns | Action |
| --- | --- | --- |
| `executions(id, limit=None)` | A benchmark's runs and comparisons, newest first | `read_runs` |
| `execution(execution_id)` | One, with every candidate and case | `read_runs` |
| `run(id, workflow_id, *, on_event=None, cancel=None)` | The execution it saved | `run_benchmark` |
| `compare(id, workflow_ids, *, target_latency_seconds, target_cost_usd, on_event=None, cancel=None)` | The execution it saved, ranked | `run_benchmark` |

A `BenchmarkExecutionSummary` has the execution's ID, its kind (`run` or
`compare`, the command that saved it), the benchmark and the revision it
ran, its workflows best first with how many cases each passed of how many,
its label and when it was recorded. An execution records the benchmark's
content, not its revision number, so the revision is the latest holding
that content, or `None` when none does. A `BenchmarkExecutionDetail` adds
each workflow's strategies, pass counts by comparison, run failures and
judge totals, and each case's result: the case, its run and evaluation,
whether it passed, and its score and reason while its evaluation is kept;
a comparison adds its scoring policy and each workflow's scorecard.
Executions of a benchmark since removed stay readable, as `benchmark
executions` keeps them.

`run` and `compare` check everything before any case runs, as the command
line does: a comparison no evaluator supports, or a workflow that declares
no result, is `invalid_argument`; a benchmark with no cases is
`invalid_argument`; a semantic case with no usable judge is a new error,
`JudgeUnavailableError`, code `judge_unavailable`, a conflict with the
judge rotation (ADR 0074). `compare` needs two distinct workflows or more,
or is `invalid_argument`.

**A benchmark runs live.** `on_event` receives `case_started`, with the
case and the workflow it runs, and `case_finished`, with whether it passed,
its score and its run, on the caller's thread, as a run's events are (ADR
0120). `cancel` is checked between cases. A cancelled execution keeps the
case runs it finished, as any run is kept, records no execution, and
raises `RunCancelledError`, as a cancelled run does; a benchmark half run
is never shown as its result.

## Consequences

- The editor can create a benchmark, add, edit and remove its cases, turn
  a run into a case, and run and compare workflows against it, as it runs,
  through the service API alone.
- The command line and the API cannot disagree about cases or executions,
  since the command line calls the API.
- The command line can create a benchmark and change or remove a case
  without editing a document by hand.
- A case's label can only rise, so editing never launders restricted data.
- A remote in 1.6 decides each of these by the action it is.

## Alternatives Considered

### Editing a benchmark by importing its document

Every edit is already possible by exporting, editing and importing the
whole document. It makes each caller rebuild a case's metadata, provenance
and label rules itself, and it can lower a label as easily as raise one.
One call per change keeps those rules in one place.

### Editing a case's input

A case's input is what its run received, or the file it was given; changing
it would make a different case under the same ID, and its provenance a
lie. A different input is a new case.

### Recording a cancelled execution

A partial execution would be ranked and compared beside complete ones,
though it ran only some cases. Its case runs are kept, so nothing is lost,
and only a complete execution is recorded.
