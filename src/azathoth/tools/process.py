"""Execution of tool implementations as subprocesses speaking JSON."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from azathoth.tools.exceptions import (
    ToolExecutionError,
    UnsupportedToolRuntimeError,
)
from azathoth.tools.implementation import (
    PROCESS_TOOL_RUNTIME,
    ToolImplementation,
)

PROCESS_STDERR_TAIL_CHARACTERS = 500
"""The most trailing stderr characters quoted when a process tool fails."""

PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE = "AZATHOTH_TOOL_TIMEOUT_SECONDS"
"""The variable that tells a process tool its own timeout, in seconds (ADR 0093)."""

_OUTPUT_ADAPTER = TypeAdapter(dict[str, JsonValue])


class ProcessToolExecutor:
    """Execute tool implementations as subprocesses.

    The implementation source is written to a temporary script whose path is
    appended to the declared command. The inputs are written to the
    process's stdin as one JSON object, and its stdout must be one JSON
    object. The process inherits Azathoth's environment and working
    directory, so a tool can itself invoke `azathoth`.

    When the implementation declares a timeout, the process sees it in
    `AZATHOTH_TOOL_TIMEOUT_SECONDS`, so it can pace itself. A process
    without a timeout never sees one, even when Azathoth itself runs inside
    a tool that has one.
    """

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Execute one process implementation with structured inputs.

        Raises:
            UnsupportedToolRuntimeError: The implementation is not a process
                implementation.
            ToolExecutionError: The command could not be started, timed out,
                exited unsuccessfully, or did not write a JSON object.
        """

        command = self._require_command(implementation)

        with tempfile.TemporaryDirectory(
            prefix="azathoth-tool-",
        ) as directory:
            script = Path(directory) / "tool"

            script.write_text(
                implementation.source,
                encoding="utf-8",
            )

            process = await self._start(
                implementation,
                (*command, str(script)),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(
                        json.dumps(inputs).encode("utf-8"),
                    ),
                    timeout=implementation.timeout_seconds,
                )
            except TimeoutError as exc:
                raise ToolExecutionError(
                    f"Tool implementation {implementation.id} timed out after "
                    f"{implementation.timeout_seconds:g} seconds."
                ) from exc
            finally:
                #
                # A timed-out or cancelled tool never outlives its step.
                #
                if process.returncode is None:
                    process.kill()
                    await process.wait()

        if process.returncode != 0:
            raise ToolExecutionError(
                self._exit_message(
                    implementation,
                    process.returncode,
                    stderr,
                )
            )

        return self._decode_output(
            implementation,
            stdout,
        )

    @staticmethod
    def _require_command(
        implementation: ToolImplementation,
    ) -> tuple[str, ...]:
        """Return the command of a process implementation."""

        if implementation.runtime != PROCESS_TOOL_RUNTIME:
            raise UnsupportedToolRuntimeError(
                "ProcessToolExecutor only supports the 'process' runtime."
            )

        if implementation.command is None:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} does not declare a command."
            )

        return implementation.command

    @staticmethod
    def _environment(
        implementation: ToolImplementation,
    ) -> dict[str, str]:
        """Return Azathoth's environment with the implementation's own timeout."""

        environment = {
            name: value
            for name, value in os.environ.items()
            if name != PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE
        }

        if implementation.timeout_seconds is not None:
            environment[PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE] = repr(
                implementation.timeout_seconds
            )

        return environment

    @classmethod
    async def _start(
        cls,
        implementation: ToolImplementation,
        arguments: tuple[str, ...],
    ) -> asyncio.subprocess.Process:
        """Start the implementation's process with piped standard streams."""

        try:
            return await asyncio.create_subprocess_exec(
                *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cls._environment(implementation),
            )
        except FileNotFoundError as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} command {arguments[0]!r} was not found."
            ) from exc
        except OSError as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} command "
                f"{arguments[0]!r} could not be started."
            ) from exc

    @staticmethod
    def _exit_message(
        implementation: ToolImplementation,
        returncode: int | None,
        stderr: bytes,
    ) -> str:
        """Return the failure message of a process that exited unsuccessfully."""

        tail = stderr.decode("utf-8", errors="replace").strip()[-PROCESS_STDERR_TAIL_CHARACTERS:]

        message = f"Tool implementation {implementation.id} exited with status {returncode}"

        if not tail:
            return f"{message}."

        return f"{message}: {tail}"

    @staticmethod
    def _decode_output(
        implementation: ToolImplementation,
        stdout: bytes,
    ) -> dict[str, JsonValue]:
        """Decode the JSON object a process wrote to stdout."""

        try:
            return _OUTPUT_ADAPTER.validate_python(
                json.loads(stdout.decode("utf-8")),
            )
        except (UnicodeDecodeError, ValueError, ValidationError) as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} produced invalid output."
            ) from exc


__all__ = [
    "PROCESS_STDERR_TAIL_CHARACTERS",
    "PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE",
    "ProcessToolExecutor",
]
