"""Tests for the environment a process tool runs with (ADR 0099)."""

import asyncio
import os
import sys
from collections.abc import Mapping
from uuid import UUID

import pytest
from pydantic import JsonValue

from azathoth.standard import standard_tool_documents
from azathoth.tools import (
    PROCESS_TOOL_RUNTIME,
    PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE,
    ProcessToolExecutor,
    ToolImplementation,
)
from azathoth.tools.environment import (
    POSIX_BASE_ENVIRONMENT,
    WINDOWS_BASE_ENVIRONMENT,
    base_environment,
    grant_matches,
    granted,
    process_tool_environment,
)

TOOL_ID = UUID("4e5f6a7b-8c9d-4e0f-8a1b-3c4d5e6f7a01")

IMPLEMENTATION_ID = UUID("4e5f6a7b-8c9d-4e0f-8a1b-3c4d5e6f7a11")

SECRETS = {
    "OPENROUTER_API_KEY": "sk-or-secret",
    "AZATHOTH_DATABASE": "/var/azathoth/azathoth.db",
    "AWS_ACCESS_KEY_ID": "AKIA0000",
    "AWS_SECRET_ACCESS_KEY": "aws-secret",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/abc",
    "OTEL_EXPORTER_OTLP_HEADERS": "authorization=Bearer otel-secret",
    "DATABASE_URL": "postgresql://user:password@host/db",
}

POSIX_ENVIRONMENT = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/Users/you",
    "USER": "you",
    "LOGNAME": "you",
    "SHELL": "/bin/zsh",
    "LANG": "en_US.UTF-8",
    "LC_ALL": "en_US.UTF-8",
    "LC_CTYPE": "UTF-8",
    "TZ": "America/New_York",
    "TMPDIR": "/var/folders/tmp",
    "TERM": "xterm-256color",
    "PYTHONPATH": "/somewhere",
    "VIRTUAL_ENV": "/Users/you/.venv",
    "SSH_AUTH_SOCK": "/private/tmp/ssh-agent",
    **SECRETS,
}

POSIX_BASE_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TERM",
    }
)

POSIX_BASE = {name: value for name, value in POSIX_ENVIRONMENT.items() if name in POSIX_BASE_NAMES}

WINDOWS_ENVIRONMENT = {
    "Path": "C:\\Windows\\system32;C:\\Python313",
    "PATHEXT": ".COM;.EXE;.BAT",
    "SystemRoot": "C:\\Windows",
    "SystemDrive": "C:",
    "windir": "C:\\Windows",
    "ComSpec": "C:\\Windows\\system32\\cmd.exe",
    "TEMP": "C:\\Users\\you\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\you\\AppData\\Local\\Temp",
    "USERPROFILE": "C:\\Users\\you",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\you",
    "APPDATA": "C:\\Users\\you\\AppData\\Roaming",
    "LOCALAPPDATA": "C:\\Users\\you\\AppData\\Local",
    "ProgramData": "C:\\ProgramData",
    "NUMBER_OF_PROCESSORS": "8",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "OS": "Windows_NT",
    "USERNAME": "you",
    **SECRETS,
}


def create_implementation(
    *,
    environment: tuple[str, ...] = (),
    timeout_seconds: float | None = None,
    source: str = "print('{}')\n",
) -> ToolImplementation:
    """Create one process implementation with the given grants."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=source,
        command=(sys.executable,),
        timeout_seconds=timeout_seconds,
        environment=environment,
    )


def posix(
    implementation: ToolImplementation,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build one implementation's environment as on macOS or Linux."""

    return process_tool_environment(
        implementation,
        POSIX_ENVIRONMENT if environ is None else environ,
        windows=False,
    )


def windows(
    implementation: ToolImplementation,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build one implementation's environment as on Windows."""

    return process_tool_environment(
        implementation,
        WINDOWS_ENVIRONMENT if environ is None else environ,
        windows=True,
    )


# Matching grants


@pytest.mark.parametrize(
    ("grant", "name", "expected"),
    [
        ("HOME", "HOME", True),
        ("HOME", "HOMEPATH", False),
        ("HOME", "home", False),
        ("AWS_*", "AWS_REGION", True),
        ("AWS_*", "AWS_", True),
        ("AWS_*", "AWS", False),
        ("AWS_*", "MY_AWS_KEY", False),
        ("LC_*", "LC_ALL", True),
    ],
)
def test_a_grant_matches_its_name_or_prefix_exactly(
    grant: str,
    name: str,
    expected: bool,
) -> None:
    assert grant_matches(grant, name) is expected


def test_a_grant_may_match_in_any_case() -> None:
    assert grant_matches("SYSTEMROOT", "SystemRoot", case_insensitive=True)
    assert grant_matches("aws_*", "AWS_REGION", case_insensitive=True)
    assert not grant_matches("SYSTEMROOT", "SystemRoot")


def test_any_of_several_grants_covers_a_name() -> None:
    assert granted("TZ", ("PATH", "TZ"))
    assert not granted("TZ", ("PATH", "T"))
    assert not granted("TZ", ())


def test_each_platform_has_its_own_base_set() -> None:
    assert base_environment(windows=False) == POSIX_BASE_ENVIRONMENT
    assert base_environment(windows=True) == WINDOWS_BASE_ENVIRONMENT
    assert "LC_*" in POSIX_BASE_ENVIRONMENT
    assert "SYSTEMROOT" in WINDOWS_BASE_ENVIRONMENT


# Building the environment on macOS and Linux


def test_a_tool_without_grants_receives_only_the_base_set() -> None:
    assert posix(create_implementation()) == POSIX_BASE


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_secrets_are_stripped(
    name: str,
) -> None:
    assert name not in posix(create_implementation())


@pytest.mark.parametrize("name", ["PYTHONPATH", "VIRTUAL_ENV", "SSH_AUTH_SOCK"])
def test_other_variables_outside_the_base_set_are_stripped(
    name: str,
) -> None:
    assert name not in posix(create_implementation())


def test_a_tool_receives_the_variables_it_grants_by_name() -> None:
    environment = posix(
        create_implementation(environment=("OPENROUTER_API_KEY", "AZATHOTH_DATABASE")),
    )

    assert environment == {
        **POSIX_BASE,
        "OPENROUTER_API_KEY": "sk-or-secret",
        "AZATHOTH_DATABASE": "/var/azathoth/azathoth.db",
    }


def test_a_tool_receives_the_variables_it_grants_by_prefix() -> None:
    environment = posix(create_implementation(environment=("AWS_*",)))

    assert {name for name in environment if name.startswith("AWS_")} == {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    }
    assert "OPENROUTER_API_KEY" not in environment


def test_a_granted_variable_azathoth_does_not_have_stays_absent() -> None:
    environment = posix(create_implementation(environment=("GITHUB_TOKEN",)))

    assert "GITHUB_TOKEN" not in environment
    assert environment == POSIX_BASE


def test_a_base_variable_azathoth_does_not_have_stays_absent() -> None:
    environment = posix(create_implementation(), {"PATH": "/usr/bin"})

    assert environment == {"PATH": "/usr/bin"}


def test_posix_grants_are_case_sensitive() -> None:
    environment = posix(
        create_implementation(environment=("openrouter_api_key",)),
    )

    assert "OPENROUTER_API_KEY" not in environment


# The managed timeout


def test_a_tool_with_a_timeout_sees_it() -> None:
    environment = posix(create_implementation(timeout_seconds=12.5))

    assert environment[PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE] == "12.5"


def test_an_inherited_timeout_never_reaches_a_tool_without_one() -> None:
    environ = {**POSIX_ENVIRONMENT, PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE: "7200"}

    environment = posix(create_implementation(environment=("AZATHOTH_*",)), environ)

    assert PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE not in environment
    assert environment["AZATHOTH_DATABASE"] == "/var/azathoth/azathoth.db"


def test_a_tools_own_timeout_replaces_an_inherited_one() -> None:
    environ = {**POSIX_ENVIRONMENT, PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE: "7200"}

    environment = posix(create_implementation(timeout_seconds=30), environ)

    assert environment[PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE] == "30.0"


# Building the environment on Windows


def test_windows_tools_receive_the_windows_base_set_in_any_case() -> None:
    environment = windows(create_implementation())

    assert environment == {
        name: value
        for name, value in WINDOWS_ENVIRONMENT.items()
        if name not in SECRETS and name != "USERNAME"
    }
    assert environment["SystemRoot"] == "C:\\Windows"
    assert environment["Path"] == "C:\\Windows\\system32;C:\\Python313"


def test_windows_strips_secrets_and_variables_outside_the_base_set() -> None:
    environment = windows(create_implementation())

    assert set(environment).isdisjoint(SECRETS)
    assert "USERNAME" not in environment


def test_windows_grants_match_in_any_case() -> None:
    environ = {**WINDOWS_ENVIRONMENT, "OpenRouter_Api_Key": "sk-or-secret"}

    environment = windows(create_implementation(environment=("OPENROUTER_API_KEY",)), environ)

    assert environment["OpenRouter_Api_Key"] == "sk-or-secret"


def test_windows_strips_an_inherited_timeout_in_any_case() -> None:
    environ = {**WINDOWS_ENVIRONMENT, "azathoth_tool_timeout_seconds": "7200"}

    environment = windows(create_implementation(environment=("AZATHOTH_*",)), environ)

    assert "azathoth_tool_timeout_seconds" not in environment


def test_the_platform_defaults_to_the_one_azathoth_runs_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZATHOTH_ENVIRONMENT_TEST_SECRET", "hidden")

    environment = process_tool_environment(create_implementation())

    assert "AZATHOTH_ENVIRONMENT_TEST_SECRET" not in environment
    assert path_variables(environment) == path_variables(os.environ)


def path_variables(
    environ: Mapping[str, str],
) -> dict[str, str]:
    """Return the search path variable, however the platform spells its name."""

    return {name: value for name, value in environ.items() if name.upper() == "PATH"}


# A real subprocess


def run(
    implementation: ToolImplementation,
) -> dict[str, JsonValue]:
    """Execute one implementation as a real subprocess."""

    return asyncio.run(ProcessToolExecutor().execute(implementation, {}))


ENVIRONMENT_SCRIPT = "import json, os\nprint(json.dumps({'names': sorted(os.environ)}))\n"


def test_a_real_process_sees_exactly_the_built_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)

    implementation = create_implementation(
        environment=("AWS_*",),
        timeout_seconds=30,
        source=ENVIRONMENT_SCRIPT,
    )

    names = run(implementation)["names"]

    assert isinstance(names, list)

    expected = set(process_tool_environment(implementation))

    #
    # A platform may add a variable to every new process, such as macOS's
    # __CF_USER_TEXT_ENCODING; none of them is a secret.
    #
    assert expected <= set(names)
    ungranted = {name for name in SECRETS if not name.startswith("AWS_")}

    assert set(names).isdisjoint(ungranted)
    assert "AWS_SECRET_ACCESS_KEY" in names
    assert PROCESS_TOOL_TIMEOUT_ENVIRONMENT_VARIABLE in names


# The standard tools


CHILD_GRANTS = ("AZATHOTH_DATABASE", "OPENROUTER_API_KEY", "AZATHOTH_WORKFLOW_DEPTH")


@pytest.mark.parametrize(
    ("name", "version"),
    [("run_workflow", "1.0.1"), ("loop_workflow", "1.1.1")],
)
def test_the_standard_tools_grant_what_their_child_process_needs(
    name: str,
    version: str,
) -> None:
    (document,) = (
        document for document in standard_tool_documents() if document.definition.name == name
    )

    (implementation,) = document.implementations

    assert implementation.environment == CHILD_GRANTS
    assert implementation.version == version


def test_the_standard_tools_see_the_database_and_key_but_no_other_secret() -> None:
    for document in standard_tool_documents():
        (implementation,) = document.implementations

        environment = posix(implementation)

        assert environment["AZATHOTH_DATABASE"] == "/var/azathoth/azathoth.db"
        assert environment["OPENROUTER_API_KEY"] == "sk-or-secret"
        assert "AWS_SECRET_ACCESS_KEY" not in environment
        assert "OTEL_EXPORTER_OTLP_HEADERS" not in environment
        assert "DATABASE_URL" not in environment
