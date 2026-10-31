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

## Version Authority

Azathoth records its version in:

```text
pyproject.toml
src/azathoth/__init__.py
```

The installed-distribution tests require both values to agree, and the release
workflow refuses a tag that does not match `pyproject.toml`.

A release version must therefore be updated in both locations, in a commit
merged to `main`, before it is tagged.

PyPI never accepts the same version twice, even after a release is deleted.
A version that was published wrongly is fixed by publishing the next version.

## Release Prerequisites

Create and activate a development environment.

macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
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
- the same on TestPyPI, with the environment `testpypi`;
- recommended: a required reviewer on the `pypi` environment, under
  Settings → Environments in GitHub, so a pushed tag waits for approval before
  anything reaches PyPI.

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
python -m mypy src/azathoth tests
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
3. it builds the source distribution and wheel with `python -m build`;
4. it installs the wheel into a clean environment, outside the checkout, and
   requires `azathoth --version` to print `azathoth <version>` and
   `azathoth --help` to succeed; and
5. it passes those same files, unchanged, to the publishing job.

Nothing is rebuilt between validation and publication.

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

### 1. Build the wheel from `main`

From the checkout, with the development venv active:

```bash
git switch main
git pull
rm -rf dist
python -m build
ls dist
deactivate
```

### 2. Install it into a fresh venv

Install the wheel into a venv outside the checkout, with a database of its
own. Stay in the checkout afterwards: the example commands use its paths.

```bash
rm -rf ~/azathoth-release-check
mkdir ~/azathoth-release-check
python3 -m venv ~/azathoth-release-check/.venv
source ~/azathoth-release-check/.venv/bin/activate
python -m pip install dist/azathoth_ai-*.whl
export AZATHOTH_DATABASE="$HOME/azathoth-release-check/examples.db"
```

Confirm that the command, the `python` on the `PATH` and the imported package
all come from the fresh venv, not from the checkout:

```bash
azathoth --version
command -v python
python -c "import azathoth; print(azathoth.__file__)"
```

All three should point inside `~/azathoth-release-check/.venv`, and the
version should be the release version.

### 3. Run the provider-free examples

With `OPENROUTER_API_KEY` unset in this terminal:

```bash
unset OPENROUTER_API_KEY

azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth tool import examples/tools/run-workflow.json
azathoth tool import examples/tools/countdown-step.json
azathoth tool import examples/tools/loop-workflow.json

azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow import examples/workflows/word-count-messages.json
azathoth workflow import examples/workflows/count-words-in-child.json
azathoth workflow import examples/workflows/countdown.json
azathoth workflow import examples/workflows/loop-countdown.json

azathoth tool verify 55555555-5555-5555-5555-555555555555 --version 1.0.0

azathoth workflow run a1000000-0000-4000-8000-000000000001 --input '"that is not dead which can eternal lie"' --output result

azathoth workflow promote a1000000-0000-4000-8000-000000000002
azathoth workflow run a1000000-0000-4000-8000-000000000003 --input '{"workflow_id": "a1000000-0000-4000-8000-000000000002", "input": "the old ones wait"}' --output result

azathoth workflow promote a1000000-0000-4000-8000-000000000004
azathoth workflow run a1000000-0000-4000-8000-000000000005 --input '{"workflow_id": "a1000000-0000-4000-8000-000000000004", "max_iterations": 10, "state": {"remaining": 3}}' --output result
```

The three runs must print exactly `8`, `4` and `[3, 2, 1]`, and the tool's
test cases must pass. The child and loop runs prove that the process tools
find the installed package through the venv's `python`.

### 4. Run the model-backed examples

Set the key (see [Connecting OpenRouter](docs/openrouter.md)), authorize
models and add a judge. Then work through examples 2 and 5 to 7 of the
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

The novel (example 8) is optional because of its cost. When it is run, a
three-chapter book is enough.

### 5. Clean up

```bash
deactivate
rm -rf ~/azathoth-release-check
```

A failure in this run blocks the release, just as a failing test would. Fix
it on a branch, merge, and run it again from step 1.

## Trial Release on TestPyPI

Before the first release, and whenever the release workflow changes, publish
the release candidate to TestPyPI:

1. merge the release commit to `main`;
2. in GitHub, open Actions → Release → Run workflow, and run it on `main`.

A manual run builds and validates exactly as a tagged run does, then publishes
to TestPyPI instead of PyPI.

Then confirm that the published artifact installs and works. Use a fresh venv,
not the one from the pre-release run, from inside the checkout:

```bash
rm -rf ~/azathoth-testpypi-check
python3 -m venv ~/azathoth-testpypi-check/.venv
source ~/azathoth-testpypi-check/.venv/bin/activate
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "azathoth-ai==<version>"
export AZATHOTH_DATABASE="$HOME/azathoth-testpypi-check/examples.db"
azathoth --version
```

Repeat step 3 of the [Pre-Release Examples Run](#pre-release-examples-run):
the provider-free examples must print `8`, `4` and `[3, 2, 1]`. Then clean
up:

```bash
deactivate
rm -rf ~/azathoth-testpypi-check
```

`--extra-index-url` lets `pip` take Azathoth's dependencies from PyPI, because
TestPyPI does not carry them. Pinning `==<version>` makes sure the trial
version is what was installed.

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
git tag -a v1.0.0 -m "Azathoth 1.0.0"
git push origin v1.0.0
```

The workflow then builds, validates and publishes to PyPI. When the `pypi`
environment has a required reviewer, the publishing job waits for that
approval.

Push a release tag once. Never move or reuse a tag that has been pushed. A tag
pushed by mistake, before anything was published, is removed with:

```bash
git tag -d v<version>
git push origin --delete v<version>
```

After publication, create the GitHub Release from the tag with the release
notes:

```bash
gh release create v<version> --title "Azathoth <version>" --notes-file <NOTES_FILE>
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

Live verification tests provider compatibility. It does not replace
deterministic release validation.

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
