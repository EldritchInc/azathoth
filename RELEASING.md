# Releasing Azathoth

Azathoth releases are Python distributions built from the repository's declared
project metadata, then published to PyPI by the release workflow,
`.github/workflows/release.yml`.

Release artifacts must be reproducible from a clean checkout and must pass the
same deterministic validation required during normal development.

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

## Trial Release on TestPyPI

Before the first release, and whenever the release workflow changes, publish
the release candidate to TestPyPI:

1. merge the release commit to `main`;
2. in GitHub, open Actions → Release → Run workflow, and run it on `main`.

A manual run builds and validates exactly as a tagged run does, then publishes
to TestPyPI instead of PyPI. Confirm the result installs:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ azathoth-ai
azathoth --version
```

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
trial release on TestPyPI
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
