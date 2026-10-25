"""Dispatch of tool implementations to the executor for their runtime."""

from collections.abc import Mapping

from pydantic import JsonValue

from azathoth.tools.exceptions import UnsupportedToolRuntimeError
from azathoth.tools.execution import (
    PYTHON_TOOL_RUNTIME,
    PythonToolExecutor,
)
from azathoth.tools.implementation import (
    PROCESS_TOOL_RUNTIME,
    ToolImplementation,
)
from azathoth.tools.process import ProcessToolExecutor
from azathoth.tools.protocols import ToolExecutor


def default_tool_executors() -> dict[str, ToolExecutor]:
    """Return a fresh executor for every runtime Azathoth supports."""

    return {
        PROCESS_TOOL_RUNTIME: ProcessToolExecutor(),
        PYTHON_TOOL_RUNTIME: PythonToolExecutor(),
    }


def supported_tool_runtimes() -> tuple[str, ...]:
    """Return the names of every runtime Azathoth supports, sorted."""

    return tuple(sorted(default_tool_executors()))


def unsupported_runtime_message(
    implementation: ToolImplementation,
) -> str:
    """Return the operator-facing rejection of an implementation's runtime."""

    return (
        f"Tool implementation {implementation.id} uses unsupported runtime "
        f"{implementation.runtime!r}; supported runtimes: "
        f"{', '.join(supported_tool_runtimes())}."
    )


class RuntimeToolExecutor:
    """Execute each tool implementation with the executor for its runtime."""

    def __init__(
        self,
        executors: Mapping[str, ToolExecutor] | None = None,
    ) -> None:
        self._executors = dict(executors) if executors is not None else default_tool_executors()

    @property
    def runtimes(self) -> tuple[str, ...]:
        """Return the runtimes this executor can execute, sorted."""

        return tuple(sorted(self._executors))

    def supports(
        self,
        runtime: str,
    ) -> bool:
        """Return whether an executor is registered for the runtime."""

        return runtime in self._executors

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Execute one implementation with the executor for its runtime.

        Raises:
            UnsupportedToolRuntimeError: No executor is registered for the
                implementation's runtime.
        """

        executor = self._executors.get(implementation.runtime)

        if executor is None:
            raise UnsupportedToolRuntimeError(
                f"No tool executor supports runtime {implementation.runtime!r}."
            )

        return await executor.execute(
            implementation,
            inputs,
        )


__all__ = [
    "RuntimeToolExecutor",
    "default_tool_executors",
    "supported_tool_runtimes",
    "unsupported_runtime_message",
]
