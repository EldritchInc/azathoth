"""Static tests that CI tests the image and releases publish and sign it (ADR 0101, ADR 0109).

The workflows are read as text, so no YAML parser is needed.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

IMAGE = "ghcr.io/eldritchinc/azathoth"


def job(
    workflow: str,
    name: str,
) -> str:
    """Return the text of one job, up to the next job or the end of the workflow."""

    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    match = re.search(rf"^  {re.escape(name)}:\n(?P<body>(?:(?:    .*)?\n)*)", text, re.MULTILINE)

    assert match is not None, f"{workflow} has no job {name}"

    return match.group("body")


# CI


def test_ci_builds_the_image_and_runs_its_tests() -> None:
    container = job("ci.yml", "container")

    assert "uses: docker/build-push-action@" in container
    assert "load: true" in container
    assert "tags: azathoth:ci" in container
    assert 'AZATHOTH_RUN_CONTAINER_TESTS: "1"' in container
    assert "AZATHOTH_CONTAINER_IMAGE: azathoth:ci" in container
    assert "run: python -m pytest tests/container -ra" in container


def test_the_test_matrix_never_needs_docker() -> None:
    tests = job("ci.yml", "tests")

    assert "AZATHOTH_RUN_CONTAINER_TESTS" not in tests
    assert "docker/" not in tests


# Release


def test_the_release_publishes_the_image_only_after_the_wheel() -> None:
    publish = job("release.yml", "publish-image")

    assert re.search(r"needs:\n      - build\n      - publish-pypi\n", publish)
    assert "needs.publish-pypi.result == 'success'" in publish
    assert "github.event_name == 'workflow_dispatch'" in publish
    assert "version: ${{ steps.version.outputs.version }}" in job("release.yml", "build")


def test_the_release_checks_the_images_version_before_pushing() -> None:
    publish = job("release.yml", "publish-image")

    check = publish.index('reported="$(docker run --rm azathoth:release --version)"')
    login = publish.index("uses: docker/login-action@")
    push = publish.index("push: ${{ github.event_name == 'push' }}")

    assert check < login < push
    assert '"${reported}" != "azathoth ${VERSION}"' in publish


def test_the_release_pushes_both_architectures_to_ghcr_only_on_a_tag() -> None:
    publish = job("release.yml", "publish-image")

    assert f"IMAGE: {IMAGE}" in publish
    assert "platforms: linux/amd64,linux/arm64" in publish
    assert "registry: ghcr.io" in publish
    assert "password: ${{ secrets.GITHUB_TOKEN }}" in publish
    assert "if: github.event_name == 'push'" in publish
    assert "packages: write" in publish


def test_the_release_tags_the_version_its_minor_line_and_latest() -> None:
    publish = job("release.yml", "publish-image")

    assert 'echo "${IMAGE}:${VERSION}"' in publish
    assert 'echo "${IMAGE}:${VERSION%.*}"' in publish
    assert 'echo "${IMAGE}:latest"' in publish
    assert "tags: ${{ steps.tags.outputs.tags }}" in publish


def test_the_release_labels_the_image_with_its_version_and_commit() -> None:
    publish = job("release.yml", "publish-image")

    assert "org.opencontainers.image.version=${{ env.VERSION }}" in publish
    assert "org.opencontainers.image.revision=${{ github.sha }}" in publish


def test_only_the_image_job_may_write_packages() -> None:
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert text.count("packages: write") == 1
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)


# The supply chain


def test_the_release_attests_an_sbom_and_full_provenance() -> None:
    publish = job("release.yml", "publish-image")
    push = publish[publish.index("name: Build for every architecture, and push on a tag") :]

    assert "id: push" in push
    assert "sbom: true" in push
    assert "provenance: mode=max" in push


def test_the_release_signs_the_pushed_image_by_its_digest_only_on_a_tag() -> None:
    publish = job("release.yml", "publish-image")

    push = publish.index("name: Build for every architecture, and push on a tag")
    install = publish.index("name: Install cosign")
    sign = publish.index('cosign sign --yes "${IMAGE}@${DIGEST}"')

    assert push < install < sign
    assert "uses: sigstore/cosign-installer@" in publish[install:sign]
    assert "DIGEST: ${{ steps.push.outputs.digest }}" in publish
    assert publish[install:].count("if: github.event_name == 'push'") == 2
    assert "id-token: write" in publish


def test_only_the_publishing_jobs_may_mint_identity_tokens() -> None:
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert text.count("id-token: write") == 3

    for name in ("publish-pypi", "publish-testpypi", "publish-image"):
        assert "id-token: write" in job("release.yml", name)

    assert "id-token: write" not in job("release.yml", "build")


def test_dependabot_keeps_the_base_images_digest_current() -> None:
    text = (PROJECT_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert "version: 2" in text
    assert re.search(
        r'- package-ecosystem: "docker"\n    directory: "/"\n    schedule:\n'
        r'      interval: "weekly"',
        text,
    )


def test_the_container_guide_verifies_the_signature_this_workflow_makes() -> None:
    guide = (PROJECT_ROOT / "docs" / "container.md").read_text(encoding="utf-8")
    identity = (
        "https://github.com/EldritchInc/azathoth/.github/workflows/release.yml@refs/tags/v1.1.0"
    )

    assert (WORKFLOWS / "release.yml").exists()
    assert guide.count(f"--certificate-identity {identity}") == 2
    assert guide.count("--certificate-oidc-issuer https://token.actions.githubusercontent.com") == 2
