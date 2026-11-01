"""Tests that build and run the container image (ADR 0101).

They need Docker, so they run only with `AZATHOTH_RUN_CONTAINER_TESTS=1`:

    make container-test

`AZATHOTH_CONTAINER_IMAGE` names an image already built, such as the one CI
builds; without it, the image is built from the checkout first.
"""

import json
import os
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from azathoth import __version__
from azathoth.jobs import JobResult, JobStatus

PROJECT_ROOT = Path(__file__).parents[2]

RUN_CONTAINER_TESTS = os.environ.get("AZATHOTH_RUN_CONTAINER_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_CONTAINER_TESTS,
    reason="Container tests require Docker and AZATHOTH_RUN_CONTAINER_TESTS=1.",
)

BUILT_IMAGE = "azathoth:container-test"

DATA = "/var/lib/azathoth"

EXAMPLES = "/examples"

CHILD_WORKFLOW_ID = "a1000000-0000-4000-8000-000000000002"

PARENT_WORKFLOW_ID = "a1000000-0000-4000-8000-000000000003"

PARENT_INPUT = json.dumps(
    {"workflow_id": CHILD_WORKFLOW_ID, "input": "the old ones wait — and dream"},
    ensure_ascii=False,
)

BUILD_TIMEOUT_SECONDS = 1800

RUN_TIMEOUT_SECONDS = 180


def docker(
    *arguments: str,
    stdin: str | None = None,
    timeout: float = RUN_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run one docker command, capturing its output as UTF-8."""

    return subprocess.run(
        ("docker", *arguments),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def succeeded(
    completed: subprocess.CompletedProcess[str],
) -> subprocess.CompletedProcess[str]:
    """Require one docker command to have succeeded, showing its stderr if not."""

    assert completed.returncode == 0, completed.stderr

    return completed


@pytest.fixture(scope="module")
def image() -> str:
    """Return the image under test, building it from the checkout unless one is named."""

    named = os.environ.get("AZATHOTH_CONTAINER_IMAGE")

    if named:
        return named

    succeeded(
        docker(
            "build",
            "--tag",
            BUILT_IMAGE,
            str(PROJECT_ROOT),
            timeout=BUILD_TIMEOUT_SECONDS,
        )
    )

    return BUILT_IMAGE


@dataclass(frozen=True)
class Deployment:
    """A data volume holding the child-workflow example, promoted."""

    image: str
    volume: str

    def run(
        self,
        *arguments: str,
        options: tuple[str, ...] = (),
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one azathoth command in a fresh container over the deployment's data."""

        return docker(
            "run",
            "--rm",
            *(("--interactive",) if stdin is not None else ()),
            "--volume",
            f"{self.volume}:{DATA}",
            "--volume",
            f"{PROJECT_ROOT / 'examples'}:{EXAMPLES}:ro",
            *options,
            self.image,
            *arguments,
            stdin=stdin,
        )


@pytest.fixture(scope="module")
def deployment(
    image: str,
) -> Iterator[Deployment]:
    """Initialize a fresh named volume and deploy the child-workflow example into it.

    A named volume starts with the image's own data folder, owned by the
    image's user, so it works wherever Docker runs.
    """

    volume = f"azathoth-container-test-{uuid.uuid4().hex[:12]}"

    succeeded(docker("volume", "create", volume))

    deployed = Deployment(image=image, volume=volume)

    try:
        initialized = succeeded(deployed.run("init"))

        assert initialized.stdout.splitlines() == [
            f"Database: {DATA}/azathoth.db (created)",
            "Installed tool run_workflow@1.0.0 revision 1.",
            "Installed tool loop_workflow@1.1.0 revision 1.",
        ]

        for arguments in (
            ("tool", "import", f"{EXAMPLES}/tools/word-count.json"),
            ("tool", "import", f"{EXAMPLES}/tools/word-count-process.json"),
            ("workflow", "import", f"{EXAMPLES}/workflows/word-count-messages.json"),
            ("workflow", "import", f"{EXAMPLES}/workflows/count-words-in-child.json"),
            ("workflow", "promote", CHILD_WORKFLOW_ID),
        ):
            succeeded(deployed.run(*arguments))

        yield deployed
    finally:
        docker("volume", "rm", "--force", volume)


def inspected(
    image: str,
) -> dict[str, object]:
    """Return the configuration of one image."""

    output = succeeded(docker("image", "inspect", "--format", "{{json .Config}}", image)).stdout
    configuration = json.loads(output)

    assert isinstance(configuration, dict)

    return configuration


# The image


def test_the_image_prints_the_package_version(
    image: str,
) -> None:
    completed = succeeded(docker("run", "--rm", image, "--version"))

    assert completed.stdout == f"azathoth {__version__}\n"


def test_the_image_prints_help_by_default(
    image: str,
) -> None:
    completed = succeeded(docker("run", "--rm", image))

    assert completed.stdout.startswith("usage: azathoth")


def test_the_image_runs_azathoth_under_tini_as_its_own_user(
    image: str,
) -> None:
    configuration = inspected(image)

    assert configuration["Entrypoint"] == ["/usr/bin/tini", "--", "azathoth"]
    assert configuration["Cmd"] == ["--help"]
    assert configuration["User"] == "10001:10001"
    assert configuration["WorkingDir"] == DATA
    assert configuration.get("Volumes") is None


def test_the_containers_python_is_azathoths(
    image: str,
) -> None:
    completed = succeeded(
        docker(
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            image,
            "-c",
            'id -u; command -v python; python -c "import azathoth; print(azathoth.__version__)"',
        )
    )

    assert completed.stdout.splitlines() == [
        "10001",
        "/opt/azathoth/venv/bin/python",
        __version__,
    ]


def test_the_otel_extra_is_installed(
    image: str,
) -> None:
    completed = succeeded(
        docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            image,
            "-c",
            "import opentelemetry.sdk, opentelemetry.exporter.otlp.proto.http; print('ok')",
        )
    )

    assert completed.stdout == "ok\n"


def test_the_postgres_extra_is_installed(
    image: str,
) -> None:
    completed = succeeded(
        docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            image,
            "-c",
            "import psycopg; print(psycopg.pq.version() >= 150000)",
        )
    )

    assert completed.stdout == "True\n"


# Running workflows


def test_a_child_workflow_runs_in_the_container(
    deployment: Deployment,
) -> None:
    completed = succeeded(
        deployment.run(
            "workflow",
            "run",
            PARENT_WORKFLOW_ID,
            "--input",
            PARENT_INPUT,
            "--output",
            "result",
        )
    )

    assert completed.stdout == "7\n"


def test_a_job_runs_over_standard_input(
    deployment: Deployment,
) -> None:
    request = {
        "kind": "invoke",
        "version": 1,
        "idempotency_key": f"container-{uuid.uuid4().hex}",
        "workflow_id": CHILD_WORKFLOW_ID,
        "input": {"value": "the old ones wait"},
    }

    completed = deployment.run("job", "run", "-", stdin=json.dumps(request))

    (line,) = completed.stdout.splitlines()
    result = JobResult.model_validate_json(line)

    assert completed.returncode == 0, completed.stderr
    assert result.status is JobStatus.SUCCEEDED
    assert result.result == {"result": 4}


def test_the_root_filesystem_may_be_read_only(
    deployment: Deployment,
) -> None:
    completed = succeeded(
        deployment.run(
            "workflow",
            "run",
            PARENT_WORKFLOW_ID,
            "--input",
            PARENT_INPUT,
            "--output",
            "result",
            options=("--read-only", "--tmpfs", "/tmp"),
        )
    )

    assert completed.stdout == "7\n"


def test_tracing_to_the_console_leaves_stdout_alone(
    deployment: Deployment,
) -> None:
    completed = succeeded(
        deployment.run(
            "workflow",
            "run",
            PARENT_WORKFLOW_ID,
            "--input",
            PARENT_INPUT,
            "--output",
            "result",
            options=(
                "--env",
                "AZATHOTH_OTEL=1",
                "--env",
                "OTEL_TRACES_EXPORTER=console",
            ),
        )
    )

    assert completed.stdout == "7\n"
    assert '"name": "azathoth.run"' in completed.stderr
    assert '"name": "azathoth.step"' in completed.stderr
