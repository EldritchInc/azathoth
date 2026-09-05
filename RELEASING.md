# Releasing Azathoth

Azathoth releases are distributed as Python packages built from the repository's
declared project metadata.

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
conventions.

## Version Authority

Azathoth currently records its version in:

```text
pyproject.toml
src/azathoth/__init__.py
```

The installed-distribution test requires both values to agree.

A release version must therefore be updated in both locations before release
artifacts are built.

Do not publish artifacts when the distribution metadata and runtime version
disagree.

## Release Prerequisites

Create and activate a development environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The development dependencies include the tooling required to build Azathoth
without relying on an isolated build environment during deterministic
validation.

## Deterministic Validation

Before building a release, run the complete project gate:

```bash
make check
```

The normal release gate must not require:

- provider credentials;
- live model execution;
- paid API usage; or
- network access for Azathoth's deterministic tests.

Live OpenRouter tests remain optional release smoke tests and are not substitutes
for deterministic validation.

## Distribution Validation

Azathoth tests its installed distribution metadata and its built wheel
separately.

The distribution metadata tests verify:

- the public distribution name;
- version agreement;
- supported Python metadata;
- runtime dependencies;
- license metadata;
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
pytest -q tests/test_package.py tests/test_distribution_artifact.py
```

## Build Release Artifacts

Remove artifacts from previous builds:

```bash
rm -rf build dist
```

Build the distributions from the release checkout using the project's declared
build backend.

The resulting files belong under:

```text
dist/
```

Release artifacts must be built only after the intended release version is
committed.

## Inspect the Release

Before publication, inspect the contents of `dist/`.

At minimum, verify that the wheel contains:

```text
azathoth/
azathoth/py.typed
*.dist-info/METADATA
*.dist-info/entry_points.txt
```

The wheel filename uses the normalized distribution name, so `azathoth-ai`
appears as `azathoth_ai`.

## Validate the Exact Release Artifact

The release artifact—not an editable checkout—is the software being released.

Before publication:

1. run the complete deterministic project gate;
2. build the final distributions from the release commit;
3. install the final wheel into a clean environment;
4. run `azathoth --version`;
5. run `azathoth --help`;
6. verify provider-free workflow import and inspection;
7. confirm the runtime version matches the intended release version; and
8. confirm the installed `azathoth` package resolves from the installed
   distribution rather than the repository checkout.

Do not rebuild artifacts after validation without validating the replacements.

## Optional Live Verification

OpenRouter verification is explicitly opt-in.

When desired, configure:

```bash
export OPENROUTER_API_KEY="..."
export AZATHOTH_RUN_LIVE_OPENROUTER_TESTS=1
```

Optional model overrides may be configured with:

```bash
export OPENROUTER_TEST_MODEL="..."
export OPENROUTER_TEST_MODELS="model-a,model-b"
```

Live verification tests provider compatibility.

It does not replace deterministic release validation.

## Release Commit and Tag

The release commit should contain the final intended version and no unrelated
changes.

After the exact release commit and artifacts have passed validation, tag that
commit using the release version:

```bash
git tag v<version>
git push origin v<version>
```

For example:

```bash
git tag v1.0.0
git push origin v1.0.0
```

A release tag identifies source that has already passed release validation. It
should not be used as the mechanism that discovers whether the release works.

## Release Principle

Azathoth keeps release authority explicit:

```text
source
  │
  ▼
deterministic validation
  │
  ▼
versioned release commit
  │
  ▼
distribution artifacts
  │
  ▼
artifact validation
  │
  ▼
release tag
  │
  ▼
publication
```

The repository working is not sufficient.

The built artifact must work.