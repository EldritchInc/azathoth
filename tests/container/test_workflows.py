"""Static tests that CI tests the image and releases publish it (ADR 0101).

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
