# Azathoth

[![CI](https://github.com/EldritchInc/azathoth/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/EldritchInc/azathoth/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/azathoth-ai)](https://pypi.org/project/azathoth-ai/)
[![Python](https://img.shields.io/pypi/pyversions/azathoth-ai)](https://pypi.org/project/azathoth-ai/)
[![Downloads](https://img.shields.io/pypi/dm/azathoth-ai)](https://pypistats.org/packages/azathoth-ai)
[![License](https://img.shields.io/github/license/EldritchInc/azathoth)](https://github.com/EldritchInc/azathoth/blob/main/LICENSE)

> Empirical optimization for context-aware AI workflows.

Azathoth is an open-source engine for building LLM workflows by composing
them rather than coding them, improving them with measured evidence rather
than intuition, and running them in production on your own infrastructure.

You describe a workflow as a JSON document:

- prompt steps that state model requirements instead of naming models;
- tool steps;
- child workflows, loops and maps;
- the dependencies, conditions and failure policies between them.

Azathoth runs it and benchmarks it. It searches for the models that pass your
benchmark at the latency and cost you target. It deploys only what you
deliberately promote, and runs it from a queue, a container or your own
program.

```text
define ──► run ──► benchmark ──► optimize ──► promote ──► invoke production
```

## Workflows Are Composed, Not Coded

Most LLM workflows are programs: prompts in source files, models as
constants, control flow as code. Every change, whether a new model, a
reworded prompt or an extra review step, goes through engineering.

Azathoth makes building a workflow a composition activity. That moves LLM
workflows out of engineering and into the hands of the teams who run and own
them:

- **platform and DevOps teams** operate workflows like infrastructure: versioned
  revisions, explicit promotion, production state and an audit trail of
  every invocation;
- **domain experts** define what a good answer is, as benchmark cases, exact
  or judged by a model, and Azathoth measures every candidate against them;
- **engineers** write **tools**: small, versioned, tested units of
  deterministic work that workflows compose.

Writing code should be for tools, not for LLM workflows.

## Quickstart

Install it in a virtual environment. The [install guide](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md)
explains why a venv, and gives the Windows commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install azathoth-ai
azathoth --version
azathoth init
```

`azathoth init` creates the database and installs the standard tools that
ship in the package: `run_workflow`, `loop_workflow` and `map_workflow`
compose workflows from other workflows; `json_select`, `json_object`,
`json_merge` and `validate_json` reshape and check the JSON that passes
between steps; `chunk_text`, `join_text` and `render_template` split, join
and fill in text; `split_s3_object` and `read_s3_object` work with data in
S3 too large to pass between steps; and `segment_pdf` divides a PDF into
segments a model can cite.

Then take a workflow through its whole life, from a clone of this
repository. It needs no model and no API key:

```bash
git clone https://github.com/EldritchInc/azathoth.git
cd azathoth
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result
azathoth benchmark import examples/benchmarks/word-count.json
azathoth benchmark run b1000000-0000-4000-8000-000000000001 --workflow a1000000-0000-4000-8000-000000000001
azathoth workflow promote a1000000-0000-4000-8000-000000000001
azathoth workflow invoke a1000000-0000-4000-8000-000000000001 --input '"and with strange aeons even death may die"' --output result
azathoth workflow runs a1000000-0000-4000-8000-000000000001
```

The workflow counts words twice, with two different tools, so either can
fail and the other still answers. `workflow run` runs it as configured. It
prints `8`. The benchmark measures it against its cases:

```text
Cases Run: 1
Cases Passed: 1
Passed (exact): 1/1
```

`workflow promote` makes this revision production, and `workflow invoke`
runs production, which prints `{"result": 8}`. `workflow runs` lists the
evidence: one run of each kind, `production`, `benchmark` and `configured`,
each with its steps, attempts and outputs recorded.

To add a model, benchmark it and let the optimizer find a cheaper one that
still passes, follow
[Getting Started](https://github.com/EldritchInc/azathoth/blob/main/docs/getting-started.md).

## Documentation

| Guide | What it covers |
| --- | --- |
| [Installing Azathoth](https://github.com/EldritchInc/azathoth/blob/main/docs/install.md) | Python, a venv, `pip install`, checking it works, on macOS and Windows; optionally PostgreSQL and tracing |
| [Running in a Container](https://github.com/EldritchInc/azathoth/blob/main/docs/container.md) | The container image: a database volume or PostgreSQL, keys, jobs over stdin, a read-only root |
| [Running on AWS](https://github.com/EldritchInc/azathoth/blob/main/docs/aws.md) | Queue workers on Fargate behind SQS, from one CloudFormation template |
| [Serving Workflows Over MCP](https://github.com/EldritchInc/azathoth/blob/main/docs/mcp.md) | Promoted workflows as tools for Claude Desktop, IDEs and agents, over stdio or HTTP behind your identity provider |
| [Connecting OpenRouter](https://github.com/EldritchInc/azathoth/blob/main/docs/openrouter.md) | An API key, finding and authorizing models, adding judges |
| [Connecting Amazon Bedrock](https://github.com/EldritchInc/azathoth/blob/main/docs/bedrock.md) | AWS credentials, the IAM policy, pricing Bedrock models and authorizing them |
| [Getting Started](https://github.com/EldritchInc/azathoth/blob/main/docs/getting-started.md) | One workflow from import to production |
| [Examples Tour](https://github.com/EldritchInc/azathoth/blob/main/docs/examples.md) | Every example, from a word count to a novel |
| [Concepts](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md) | How Azathoth is put together, and why |
| [CLI Reference](https://github.com/EldritchInc/azathoth/blob/main/src/azathoth/cli/README.md) | Every command, its options and its output |
| [Architecture Decisions](https://github.com/EldritchInc/azathoth/blob/main/docs/adrs/README.md) | The ADRs behind each boundary |
| [Changelog](https://github.com/EldritchInc/azathoth/blob/main/CHANGELOG.md) | What each release changed, and how to upgrade |
| [Contributing](https://github.com/EldritchInc/azathoth/blob/main/CONTRIBUTING.md) | Working on Azathoth itself |
| [Releasing](https://github.com/EldritchInc/azathoth/blob/main/RELEASING.md) | How a release is validated and published |

## Examples

The [examples](https://github.com/EldritchInc/azathoth/tree/main/examples)
are complete, importable workflows, each with its benchmarks and end-to-end
tests:

- **word count**: tools, redundancy, and benchmark cases made from corrected
  runs;
- **classify sentiment**: the whole lifecycle in one step;
- **child workflow**, **countdown loop** and **word count map**: composing
  workflows;
- **ticket triage**: conditional routing to specialists, and a cheaper
  classifier found by the optimizer;
- **workflow writer**: a workflow that writes workflows and validates them;
- **code review**: three concurrent reviewers, merged by code rather than a
  model;
- **novel**: nested loops that plan, draft, edit and revise a book;
- **large file**: a file of any size in S3, split into chunks, counted by a
  map and summed.

## What Azathoth Does

- **Composes workflows** from prompt, tool and child-workflow steps. Steps can
  depend on each other, pass values by name or as constants, run
  conditionally, retry, and fail in a controlled way. Child workflows, loops
  and maps run through standard tools that ship in the package.
- **Separates intent from models.** Steps state requirements, and Azathoth
  chooses from the models you have authorized among those OpenRouter and
  Amazon Bedrock currently offer.
- **Records everything**: every run, step, attempt, prompt, reply, token and
  cost, as durable evidence, and traces it with OpenTelemetry when asked.
- **Benchmarks** workflows with exact, normalized, schema and model-judged
  semantic cases.
- **Optimizes** by trying strictly cheaper authorized models, step by step,
  and ranking candidates on quality, reliability, latency and cost. The
  report shows which model each step of the winner used.
- **Promotes deliberately.** Production runs only what was explicitly
  promoted, on exact models, with a revision history and an invocation log.
  Optimizing never deploys anything by itself.
- **Runs in production**: from versioned job requests that replay rather than
  repeat, in a signed container image, or as a fleet of queue workers on AWS
  that share one PostgreSQL database. A run interrupted by a deploy or a lost
  machine resumes from its journal.
- **Takes inputs by value or by reference**, from files or S3, and keeps the
  content each run was given. Data too large for an input stays in S3 and is
  worked in chunks.
- **Serves workflows to AI clients.** `azathoth-mcp` offers the promoted
  workflows you list as MCP tools, to Claude Desktop, IDEs and agents, over
  stdio or over HTTP behind your identity provider, a scope per tool. Every
  call is a recorded invocation that names who made it.

Azathoth is also a typed Python library. The
[package READMEs](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md#package-guide)
document each subsystem.

## Design Principles

> **Persist what should happen. Compose what can execute. Record what
> actually happened. Change production deliberately.**

- **Evidence over intuition.** A candidate is better only once it has been
  measured as better.
- **Composition over code.** Workflows are documents; code lives in tools.
- **Provider independence.** Workflows describe model requirements; providers
  are attached at run time.
- **Explicit production authority.** Production is what you promoted, not the
  latest optimizer winner or the cheapest model.
- **Immutable records.** Configuration, runs, evaluations and deployments are
  never rewritten.

[Concepts](https://github.com/EldritchInc/azathoth/blob/main/docs/concepts.md)
explains each of these in depth.

## Project Status

Azathoth 1.2 supports Python 3.11, 3.12 and 3.13 on Linux, macOS and
Windows, all tested in CI. It runs models on OpenRouter and Amazon Bedrock,
keeps its state in SQLite or PostgreSQL, ships as a signed container image
for amd64 and arm64, deploys to AWS from one CloudFormation template, and
serves promoted workflows to AI clients over MCP with `azathoth-mcp`.
The [changelog](https://github.com/EldritchInc/azathoth/blob/main/CHANGELOG.md)
lists what each release added.

Within 1.x, these stay compatible: workflow, tool and job documents, the
CLI's commands and the output it documents, and the database schema, which
`azathoth init` migrates forward. The Python API is typed and documented,
but may change in a minor release.

## Commercial Support and Pilots

Eldritch, Inc. builds and supports Azathoth. For help putting workflows
into production, a pilot on your own data, or support for a deployment,
see [Work With Us](https://eldritchinc.com/workwithus/).

## License

Azathoth is licensed under the
[MIT License](https://github.com/EldritchInc/azathoth/blob/main/LICENSE).
