"""Execution of trusted Python tool implementations."""

import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable, iscoroutinefunction
from typing import Any, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from azathoth.tools.exceptions import (
    ToolEntrypointError,
    ToolExecutionError,
    UnsupportedToolRuntimeError,
)
from azathoth.tools.implementation import ToolImplementation

PYTHON_TOOL_RUNTIME = "python"
"""The runtime name of in-process Python tool implementations."""

_OUTPUT_ADAPTER = TypeAdapter(dict[str, JsonValue])

_PYTHON_BUILTINS: dict[str, object] = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}


class PythonToolExecutor:
    """Execute trusted Python tool implementations in process.

    A synchronous entrypoint runs in a worker thread, so a slow tool never
    blocks the event loop its concurrent workflow siblings share. An async
    entrypoint is awaited on the event loop.
    """

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Execute a trusted Python implementation with structured inputs.

        Raises:
            UnsupportedToolRuntimeError: The implementation is not a Python
                implementation.
            ToolEntrypointError: The entrypoint is missing or not callable.
            ToolExecutionError: The source could not be loaded, execution
                failed, or the output is not a JSON object.
        """

        self._validate_runtime(implementation)

        namespace = self._load_namespace(implementation)
        entrypoint = self._get_entrypoint(
            implementation,
            namespace,
        )

        #
        # A plain bool keeps mypy from narrowing the entrypoint through the
        # iscoroutinefunction type guard, which no branch needs.
        #
        is_coroutine_function: bool = iscoroutinefunction(entrypoint)

        try:
            if is_coroutine_function:
                result = entrypoint(**inputs)
            else:
                result = await asyncio.to_thread(
                    entrypoint,
                    **inputs,
                )

            if isawaitable(result):
                result = await result
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} failed during execution."
            ) from exc

        return self._validate_output(
            implementation,
            result,
        )

    @staticmethod
    def _validate_runtime(
        implementation: ToolImplementation,
    ) -> None:
        """Ensure the implementation uses the Python runtime."""

        if implementation.runtime != PYTHON_TOOL_RUNTIME:
            raise UnsupportedToolRuntimeError(
                "PythonToolExecutor only supports the 'python' runtime."
            )

    @staticmethod
    def _load_namespace(
        implementation: ToolImplementation,
    ) -> dict[str, Any]:
        """Compile and load trusted implementation source."""

        namespace: dict[str, Any] = {
            "__builtins__": _PYTHON_BUILTINS.copy(),
        }

        try:
            code = compile(
                implementation.source,
                f"<tool:{implementation.id}>",
                "exec",
            )
            exec(code, namespace)
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} could not be loaded."
            ) from exc

        return namespace

    @staticmethod
    def _get_entrypoint(
        implementation: ToolImplementation,
        namespace: dict[str, Any],
    ) -> Callable[..., object | Awaitable[object]]:
        """Resolve the configured executable entrypoint."""

        entrypoint = namespace.get(implementation.entrypoint)

        if entrypoint is None:
            raise ToolEntrypointError(
                f"Tool entrypoint {implementation.entrypoint!r} was not found."
            )

        if not callable(entrypoint):
            raise ToolEntrypointError(
                f"Tool entrypoint {implementation.entrypoint!r} is not callable."
            )

        return cast(
            Callable[..., object | Awaitable[object]],
            entrypoint,
        )

    @staticmethod
    def _validate_output(
        implementation: ToolImplementation,
        result: object,
    ) -> dict[str, JsonValue]:
        """Ensure execution produced structured JSON output."""

        try:
            return _OUTPUT_ADAPTER.validate_python(result)
        except ValidationError as exc:
            raise ToolExecutionError(
                f"Tool implementation {implementation.id} produced invalid output."
            ) from exc
