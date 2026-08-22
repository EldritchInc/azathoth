"""Workflow commands for the Azathoth command-line application."""

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration


def list_workflows() -> int:
    """List configured durable workflows."""

    configuration = CliRuntimeConfiguration.from_environment()

    runtime = load_runtime(configuration)

    for specification in runtime.workflows.specifications:
        metadata = specification.metadata

        print(f"{metadata.id}  {metadata.version}  {metadata.name}")

    return 0
