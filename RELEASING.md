# Releasing Azathoth

Azathoth releases are Python distributions built from the repository's declared
project metadata, then published to PyPI by the release workflow,
`.github/workflows/release.yml`.

Release artifacts must be reproducible from a clean checkout and must pass the
same deterministic validation required during normal development.

This document gives the steps. [Release Validation](docs/release-validation.md)
defines what those steps must prove.

## Distribution Identity

The public Python distribution is:

```text
azathoth-ai
```

The import package is:

```python
import azathoth
```

The installed console command is:

```text
azathoth
```

These names intentionally differ only where required by Python package naming
conventions. The name `azathoth` on PyPI belongs to an unrelated project.

Azathoth's MCP server is a second distribution, built from
`packages/azathoth-mcp` and released with every release, at the same version
(ADR 0111):

```text
azathoth-mcp
```

Its import package is `azathoth_mcp` and its command `azathoth-mcp`. It
requires exactly its own minor release of `azathoth-ai`, so the two are
always published together, from one tag.

Each release is also published as a container image (ADR 0101):

```text
ghcr.io/eldritchinc/azathoth:<version>
```

## Version Authority

Azathoth records its version in:

```text
pyproject.toml
src/azathoth/__init__.py
packages/azathoth-mcp/pyproject.toml
packages/azathoth-mcp/src/azathoth_mcp/__init__.py
```

`azathoth-mcp`'s `azathoth-ai` requirement names the same minor release, as
`azathoth-ai==<major>.<minor>.*`. The installed-distribution tests require all
of them to agree, and the release workflow refuses a tag that does not match
`pyproject.toml`, and an `azathoth-mcp` that declares another version.

A release version must therefore be updated in every one of these, in a commit
merged to `main`, before it is tagged. Its changelog entry is the
`## Unreleased` entry, renamed to the version.

PyPI never accepts the same version twice, even after a release is deleted.
A version that was published wrongly is fixed by publishing the next version.

## Release Prerequisites

Create and activate a development environment.

macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]" -e packages/azathoth-mcp
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]" -e packages/azathoth-mcp
```

If PowerShell refuses to run the activation script, allow local scripts once
for your user, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

The development dependencies include `build`, which produces the release
artifacts.

Publishing uses PyPI Trusted Publishing, so no API token is stored anywhere.
It requires, once:

- a pending publisher on PyPI for `azathoth-ai`, naming the repository
  `EldritchInc/azathoth`, the workflow `release.yml`, and the environment
  `pypi`;
- the same for `azathoth-mcp`, which the same job publishes beside it: a
  pending publisher until its first release creates the project, and a
  trusted publisher of the project after that;
- the same two on TestPyPI, with the environment `testpypi`;
- recommended: a required reviewer on the `pypi` environment, under
  Settings → Environments in GitHub, so a pushed tag waits for approval before
  anything reaches PyPI. The image waits for the same approval, because it is
  published only after the wheel.

The image is pushed with the workflow's own `GITHUB_TOKEN`, so it needs no
secret either. After the first release creates the
`ghcr.io/eldritchinc/azathoth` package, once:

- make the package public, under the organization's Packages →
  `azathoth` → Package settings → Change visibility;
- and connect it to the `EldritchInc/azathoth` repository there, if GitHub
  did not, so the release workflow keeps permission to push it.

## Deterministic Validation

Before releasing, the complete project gate must pass.

macOS and Linux:

```bash
make check
```

Windows has no `make`, so run the same commands directly:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy src/azathoth packages/azathoth-mcp/src/azathoth_mcp tests
python -m pytest
```

Continuous integration runs lint, formatting and type checks once, and the
test suite on Linux, macOS and Windows with Python 3.11, 3.12 and 3.13. Every
check must be green on the commit being released.

The normal release gate must not require:

- provider credentials;
- live model execution;
- paid API usage; or
- network access for Azathoth's deterministic tests.

Live OpenRouter tests remain optional release smoke tests and are not
substitutes for deterministic validation.

## Distribution Validation

Azathoth tests its installed distribution metadata and its built wheel
separately.

The distribution metadata tests verify:

- the public distribution name;
- version agreement;
- supported Python metadata;
- runtime dependencies;
- license metadata;
- development status and project URLs;
- project README metadata; and
- the `azathoth` console entry point.

The wheel artifact tests verify:

- the import package is present;
- the `py.typed` marker is shipped;
- distribution metadata is present;
- the wheel installs into a separate environment;
- the installed package is loaded from that environment rather than the source
  checkout;
- the console command executes outside the repository; and
- provider-free workflow inspection works from the installed artifact.

Run the focused packaging gate with:

```bash
python -m pytest -q tests/test_package.py tests/test_distribution_artifact.py
```

## How the Release Workflow Validates the Artifact

The release artifact, not an editable checkout, is the software being
released. The workflow's `build` job validates exactly what it publishes:

1. it reads the version from `pyproject.toml`;
2. for a tag, it requires the tag to be exactly `v` followed by that version;
3. it requires `packages/azathoth-mcp/pyproject.toml` to declare the same
   version;
4. it builds the source distributions and wheels of both with
   `python -m build`;
5. it installs both wheels into a clean environment, outside the checkout,
   and requires `azathoth --version` to print `azathoth <version>`,
   `azathoth-mcp --version` to print `azathoth-mcp <version>`, and both
   commands' help to succeed; and
6. it passes those same files, unchanged, to the publishing job, which
   publishes both distributions.

Nothing is rebuilt between validation and publication.

Once the wheel is published, the `publish-image` job builds the container
image from the same commit:

1. it builds the image for `linux/amd64`, and requires `azathoth --version`
   inside it to print `azathoth <version>`, and `azathoth-mcp --version` to
   print `azathoth-mcp <version>`;
2. it builds the image for `linux/amd64` and `linux/arm64`, and pushes both
   to `ghcr.io/eldritchinc/azathoth` as `<version>`, `<major>.<minor>` and
   `latest`, labeled with the version and the commit, with an SBOM and its
   build's provenance attached;
3. it signs the pushed image by its digest with cosign, keylessly, through
   the workflow's own GitHub identity (ADR 0109).

The image's base is pinned by digest in the `Dockerfile`. Dependabot opens a
pull request when the base tag gets a new digest, so security fixes in the
base arrive through the same tests as any other change.

A manual run builds both architectures and pushes nothing. The container
image tests prove the rest on every pull request (see
[Container Tests](CONTRIBUTING.md#container-tests)).

To build and inspect the artifacts locally:

```bash
python -m build
```

The files appear under `dist/`. The wheel must contain:

```text
azathoth/
azathoth/py.typed
*.dist-info/METADATA
*.dist-info/entry_points.txt
```

The wheel filename uses the normalized distribution name, so `azathoth-ai`
appears as `azathoth_ai`.

## Pre-Release Examples Run

The deterministic suite proves the examples against controlled models. This
run proves them the way a new user meets them: from the built wheel, in a
fresh venv outside the checkout, against real models, by following
[Installing Azathoth](docs/install.md) and [Examples Tour](docs/examples.md).

Run it on macOS after the release commit is merged to `main`, and before the
TestPyPI trial. Run it in PowerShell 7 on Windows too whenever a Windows
machine is available; the guides give every command for both.

### 1. Build the wheels from `main`

From the checkout, with the development venv active, build both
distributions:

```bash
git switch main
git pull
rm -rf dist
python -m build
python -m build packages/azathoth-mcp --outdir dist
ls dist
deactivate
```

### 2. Install them into a fresh venv

Install both wheels into a venv outside the checkout, with a database of its
own, and Azathoth with its `documents` extra, as a user reading PDFs would.
`azathoth-mcp` brings the MCP SDK, which the `mcp` extra would. Stay in the
checkout afterwards: the example commands use its paths.

```bash
rm -rf ~/azathoth-release-check
mkdir ~/azathoth-release-check
python3 -m venv ~/azathoth-release-check/.venv
source ~/azathoth-release-check/.venv/bin/activate
python -m pip install "$(echo dist/azathoth_ai-*.whl)[documents]" dist/azathoth_mcp-*.whl
export AZATHOTH_DATABASE="$HOME/azathoth-release-check/examples.db"
```

Confirm that the commands, the `python` on the `PATH` and the imported
packages all come from the fresh venv, not from the checkout:

```bash
azathoth --version
azathoth-mcp --version
command -v python
python -c "import azathoth, azathoth_mcp; print(azathoth.__file__, azathoth_mcp.__file__)"
```

All of them should point inside `~/azathoth-release-check/.venv`, and both
versions should be the release version.

### 3. Run the provider-free examples

With `OPENROUTER_API_KEY` unset in this terminal:

```bash
unset OPENROUTER_API_KEY

azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth tool import examples/tools/countdown-step.json
azathoth tool install-standard

azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow import examples/workflows/count-words-in-child.json
azathoth workflow import examples/workflows/countdown.json
azathoth workflow import examples/workflows/loop-countdown.json
azathoth workflow import examples/workflows/count-words-in-item.json
azathoth workflow import examples/workflows/map-word-count.json

azathoth tool verify 55555555-5555-5555-5555-555555555555 --version 1.0.0

azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result

azathoth workflow promote a1000000-0000-4000-8000-000000000002
azathoth workflow run a1000000-0000-4000-8000-000000000003 --input '{"workflow_id": "a1000000-0000-4000-8000-000000000002", "input": "the old ones wait"}' --output result

azathoth workflow promote a1000000-0000-4000-8000-000000000004
azathoth workflow run a1000000-0000-4000-8000-000000000005 --input '{"remaining": 3}' --output result

azathoth workflow promote a1000000-0000-4000-8000-000000000006
azathoth workflow run a1000000-0000-4000-8000-000000000007 --input '["the old ones wait", "and dream", "in sunken cities"]' --output result
```

The four runs must print exactly `8`, `4`, `[3, 2, 1]` and
`[{"result": 4}, {"result": 2}, {"result": 3}]`, and the tool's test cases
must pass. `tool install-standard` proves that the standard tools ship in
the installed package, and the child, loop and map runs prove that the
process tools find that package through the venv's `python`.

### 4. Serve a workflow over MCP

Step 3 promoted the word-count workflow. Expose it, as
[Serving Workflows Over MCP](docs/mcp.md) does, beside the database, and call
it through the installed server over stdio, with the SDK's client from the
same venv:

```bash
cat > "$(dirname "$AZATHOTH_DATABASE")/exposure.json" <<'EOF'
{"version": 1, "tools": [{"workflow_id": "a1000000-0000-4000-8000-000000000002", "name": "count_words", "description": "Count the words in a piece of text.", "input_schema": {"type": "string"}}]}
EOF

python - <<'EOF'
import asyncio
import json
import os

from mcp import Client, StdioServerParameters

exposure = os.path.join(os.path.dirname(os.environ["AZATHOTH_DATABASE"]), "exposure.json")
server = StdioServerParameters(
    command="azathoth-mcp", args=["serve", "--exposure", exposure], env=dict(os.environ)
)


async def check() -> None:
    async with Client(server) as client:
        print([tool.name for tool in (await client.list_tools()).tools])
        called = await client.call_tool("count_words", {"input": "the old ones wait and dream"})
        print(json.dumps(called.structured_content["result"]))
        evidence = await client.call_tool(
            "get_invocation", {"invocation_id": called.structured_content["invocation_id"]}
        )
        print(evidence.structured_content["status"], evidence.structured_content["caller"])


asyncio.run(check())
EOF
```

It must print exactly:

```text
['count_words', 'get_invocation']
{"result": 6}
succeeded {'mcp': {'transport': 'stdio', 'tool': 'count_words'}}
```

That proves the installed server finds its document and the database,
offers only what is exposed, runs the promoted workflow as a recorded
invocation, and reads back its evidence with the caller.

### 5. Read a PDF

Step 3 installed the standard tools. Give the example claim to the workflow
that divides it with `segment_pdf`:

```bash
azathoth workflow import examples/documents/segment-claim.json
azathoth workflow run a1000000-0000-4000-8000-0000000000c0 --input-file examples/documents/claim.pdf --output result
```

The run must print exactly this line, with the installed pdfminer.six's
version and the digest of the extraction it kept in place of the
placeholders:

```text
{"extraction": {"tool": "segment_pdf", "version": "1.0.0 (pdfminer.six <PDFMINER_VERSION>; line_overlap=0.5,char_margin=2.0,line_margin=0.5,word_margin=0.1,boxes_flow=0.5)", "digest": "<EXTRACTION_DIGEST>", "source_digest": "9bc3db695946b626972580aa8ed59d6bb008c72f5ca51d79910d22c7feaaa185", "media_type": "application/pdf"}}
```

That proves the `documents` extra installs pdfminer.six from the wheel's
metadata, a PDF is accepted by reference and kept, and the standard
`segment_pdf` finds it through the venv's `python` and keeps its
extraction.

### 6. Call an MCP tool

Follow [Calling MCP Tools](docs/mcp-tools.md): write the example server's
tool document, import it, and call the tool from a workflow step:

```bash
azathoth tool from-mcp --tool count_words -- python examples/mcp/word_count_server.py > "$(dirname "$AZATHOTH_DATABASE")/count-words-mcp.json"
azathoth tool import "$(dirname "$AZATHOTH_DATABASE")/count-words-mcp.json"
azathoth workflow import examples/mcp/count-words-over-mcp.json
azathoth workflow run a1000000-0000-4000-8000-0000000000b0 --input '"the old ones wait and dream"' --output result
```

The run must print exactly `6`. That proves the server the guide names is
started over stdio by the venv's `python`, its tool's document is written
and pinned, and a step calls it.

### 7. Run the model-backed examples

Set the key (see [Connecting OpenRouter](docs/openrouter.md)), authorize
models and add a judge. Then work through examples 2 and 6 to 8 of the
[Examples Tour](docs/examples.md) in order: classify sentiment, ticket triage,
workflow writer and code review. Each must complete:

- sentiment answers `positive`, its benchmark runs, `optimize` evaluates the
  cheaper candidates in its final evaluation and reports a winner with each
  step's model, `promote --experiment` with the winning experiment ID pins
  the winner's model, and `invoke` then returns `{"result": "positive"}`;
- triage returns a complete triage record;
- the workflow writer returns `valid: true` for its sample request, and the
  extracted workflow imports;
- code review approves the pure rename with no findings;
- each benchmark with semantic cases runs with the judge.

The novel (example 9) is optional because of its cost. When it is run, a
three-chapter book is enough.

### 8. Clean up

```bash
deactivate
rm -rf ~/azathoth-release-check
```

A failure in this run blocks the release, just as a failing test would. Fix
it on a branch, merge, and run it again from step 1.

### 9. Test the image

With Docker running and the development venv active again, from the
checkout on `main`, build the release commit's image and run its tests:

```bash
source .venv/bin/activate
make container-test
```

They must pass, as they did in CI. Then follow steps 2 and 3 of
[Running in a Container](docs/container.md) once by hand, with the image you
built (`azathoth:test`) and a fresh volume, and remove the volume afterwards.

### 10. Test PostgreSQL

Still with Docker running, run the persistence tests against a throwaway
PostgreSQL server:

```bash
make postgres-test
```

They must pass, as they did in CI (see
[PostgreSQL Tests](CONTRIBUTING.md#postgresql-tests)).

## Trial Release on TestPyPI

Before the first release, and whenever the release workflow changes, publish
the release candidate to TestPyPI:

1. merge the release commit to `main`;
2. in GitHub, open Actions → Release → Run workflow, and run it on `main`.

A manual run builds and validates exactly as a tagged run does, then publishes
to TestPyPI instead of PyPI. It also builds the container image for both
architectures, and checks its version, without pushing it.

Then confirm that the published artifact installs and works. Use a fresh venv,
not the one from the pre-release run, from inside the checkout:

```bash
rm -rf ~/azathoth-testpypi-check
python3 -m venv ~/azathoth-testpypi-check/.venv
source ~/azathoth-testpypi-check/.venv/bin/activate
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "azathoth-ai[documents]==<version>" "azathoth-mcp==<version>"
export AZATHOTH_DATABASE="$HOME/azathoth-testpypi-check/examples.db"
azathoth --version
azathoth-mcp --version
```

Repeat steps 3 to 6 of the [Pre-Release Examples Run](#pre-release-examples-run):
they must print exactly what they printed there. Then clean up:

```bash
deactivate
rm -rf ~/azathoth-testpypi-check
```

`--extra-index-url` lets `pip` take Azathoth's dependencies from PyPI, because
TestPyPI does not carry them. Pinning `==<version>` makes sure the trial
versions are what was installed.

TestPyPI also never accepts the same version twice. A second trial of one
version fails at the publishing step, after validation has already passed.

## Release

A release is triggered by pushing a version tag from the merged, validated
release commit on `main`:

```bash
git switch main
git pull
git tag -a v<version> -m "Azathoth <version>"
git push origin v<version>
```

For example:

```bash
git tag -a v1.3.0 -m "Azathoth 1.3.0"
git push origin v1.3.0
```

The workflow then builds, validates and publishes to PyPI, and then
publishes the container image. When the `pypi` environment has a required
reviewer, both wait for that approval.

Confirm that the image is public, reports the release, and is signed by
the release workflow for its tag:

```bash
docker run --rm ghcr.io/eldritchinc/azathoth:<version> --version
docker run --rm --entrypoint /usr/bin/tini ghcr.io/eldritchinc/azathoth:<version> -- azathoth-mcp --version
cosign verify ghcr.io/eldritchinc/azathoth:<version> --certificate-identity https://github.com/EldritchInc/azathoth/.github/workflows/release.yml@refs/tags/v<version> --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Push a release tag once. Never move or reuse a tag that has been pushed. A tag
pushed by mistake, before anything was published, is removed with:

```bash
git tag -d v<version>
git push origin --delete v<version>
```

After publication, create the GitHub Release from the tag. Its notes are
the version's entry in [`CHANGELOG.md`](CHANGELOG.md), which the release
commit must already hold:

```bash
awk -v version=<version> '$0 == "## " version {found = 1; next} /^## / {found = 0} found' CHANGELOG.md > release-notes.md
gh release create v<version> --title "Azathoth <version>" --notes-file release-notes.md
```

A tag identifies source that has already passed validation. It is not the
mechanism that discovers whether the release works.

## Optional Live Verification

OpenRouter verification is explicitly opt-in, and may consume API credits.

macOS and Linux:

```bash
export OPENROUTER_API_KEY="..."
export AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
python -m pytest
```

Windows (PowerShell):

```powershell
$env:OPENROUTER_API_KEY = "..."
$env:AZATHOTH_RUN_LIVE_OPENROUTER_TESTS = "1"
python -m pytest
```

Optional model overrides are `OPENROUTER_TEST_MODEL` and
`OPENROUTER_TEST_MODELS` (a comma-separated list).

Bedrock verification is opt-in the same way, needs AWS credentials allowed
to call Bedrock, and may incur AWS charges. `BEDROCK_TEST_MODEL` names a
Bedrock model ID or inference profile ID the region offers:

```bash
export AWS_REGION="us-east-1"
export AZATHOTH_RUN_LIVE_BEDROCK_TESTS=1
export BEDROCK_TEST_MODEL="amazon.nova-lite-v1:0"
python -m pytest tests/providers/test_bedrock_live.py -ra
```

```powershell
$env:AWS_REGION = "us-east-1"
$env:AZATHOTH_RUN_LIVE_BEDROCK_TESTS = "1"
$env:BEDROCK_TEST_MODEL = "amazon.nova-lite-v1:0"
python -m pytest tests/providers/test_bedrock_live.py -ra
```

Live verification tests provider compatibility. It does not replace
deterministic release validation.

## AWS Deployment Check

A release that changes `deploy/aws/azathoth.yaml`, the worker, the S3 tools
or what the image runs on AWS is deployed once to a sandbox AWS account
first, as [Release Validation](docs/release-validation.md#9-the-aws-deployment)
requires. Validate the template:

```bash
aws cloudformation validate-template --template-body file://deploy/aws/azathoth.yaml
```

```powershell
aws cloudformation validate-template --template-body file://deploy/aws/azathoth.yaml
```

Then work through the rest of that section with the release's image: follow
[Running on AWS](docs/aws.md) through its job, stop one worker while a job
runs, process the large file of at least 20 MiB, and tear the stack down.
Section 9 is the authority for what each step must show.

A release that changes none of these, and changes the image only by adding
what the stack does not run, as 1.2.0 added `azathoth-mcp`, is not deployed.
Its changelog entry says so, so the release notes do.

A release that changes one of them when no sandbox account is available, as
1.3.0 did, is not deployed either. Section 9 allows it only on the record:
the changelog entry says the release was not deployed and why, what was
checked instead, and what that leaves unproven.

## Release Principle

Azathoth keeps release authority explicit:

```text
source
  │
  ▼
deterministic validation on every platform
  │
  ▼
versioned release commit on main
  │
  ▼
pre-release examples run from the built wheel
  │
  ▼
trial release on TestPyPI, installed and run
  │
  ▼
release tag
  │
  ▼
built and validated artifacts
  │
  ▼
publication to PyPI
```

The repository working is not sufficient.

The built artifact must work.
