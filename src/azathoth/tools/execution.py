"""Execution of trusted Python tool implementations."""

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from azathoth.tools.exceptions import (
    ToolEntrypointError,
    ToolExecutionError,
    UnsupportedToolRuntimeError,
)
from azathoth.tools.implementation import ToolImplementation

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
    """Execute trusted Python tool implementations in process."""

    async def execute(
        self,
        implementation: ToolImplementation,
        inputs: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        """Execute a trusted Python implementation with structured inputs."""

        self._validate_runtime(implementation)

        namespace = self._load_namespace(implementation)
        entrypoint = self._get_entrypoint(
            implementation,
            namespace,
        )

        try:
            result = entrypoint(**inputs)

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

        if implementation.runtime != "python":
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
