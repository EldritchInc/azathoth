"""The environment a process tool runs with (ADR 0099)."""

import os
from collections.abc import Iterable, Mapping
from typing import Final

from azathoth.tools.implementation import (
    ENVIRONMENT_PREFIX_WILDCARD,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    ToolImplementation,
)

POSIX_BASE_ENVIRONMENT: Final = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_*",
    "TZ",
    "TMPDIR",
    "TERM",
)
"""The variables every process tool receives on macOS and Linux, when set."""

WINDOWS_BASE_ENVIRONMENT: Final = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)
"""The variables every process tool receives on Windows, when set."""


def base_environment(
    *,
    windows: bool,
) -> tuple[str, ...]:
    """Return the base grants of one platform."""

    return WINDOWS_BASE_ENVIRONMENT if windows else POSIX_BASE_ENVIRONMENT


def grant_matches(
    grant: str,
    name: str,
    *,
    case_insensitive: bool = False,
) -> bool:
    """Return whether one grant, a name or a `PREFIX*`, covers one variable name."""

    if case_insensitive:
        grant = grant.upper()
        name = name.upper()

    if grant.endswith(ENVIRONMENT_PREFIX_WILDCARD):
        return name.startswith(grant[: -len(ENVIRONMENT_PREFIX_WILDCARD)])

    return name == grant


def granted(
    name: str,
    grants: Iterable[str],
    *,
    case_insensitive: bool = False,
) -> bool:
    """Return whether any of the grants covers one variable name."""

    return any(grant_matches(grant, name, case_insensitive=case_insensitive) for grant in grants)


def process_tool_environment(
    implementation: ToolImplementation,
    environ: Mapping[str, str] | None = None,
    *,
    windows: bool | None = None,
) -> dict[str, str]:
    """Return the environment one process implementation runs with.

    It holds the variables of Azathoth's environment that the platform's base
    set or the implementation's own grants cover, and, when the
    implementation declares a timeout, the engine-managed
    `AZATHOTH_TOOL_TIMEOUT_SECONDS`. Nothing else is inherited, so a secret
    the implementation did not grant itself never reaches it. On Windows,
    variable names match in any case.
    """

    source = os.environ if environ is None else environ
    on_windows = os.name == "nt" if windows is None else windows
    grants = (*base_environment(windows=on_windows), *implementation.environment)

    environment = {
        name: value
        for name, value in source.items()
        if not grant_matches(
            PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
            name,
            case_insensitive=on_windows,
        )
        and granted(name, grants, case_insensitive=on_windows)
    }

    if implementation.timeout_seconds is not None:
        environment[PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE] = repr(
            implementation.timeout_seconds
        )

    return environment


__all__ = [
    "POSIX_BASE_ENVIRONMENT",
    "WINDOWS_BASE_ENVIRONMENT",
    "base_environment",
    "grant_matches",
    "granted",
    "process_tool_environment",
]
