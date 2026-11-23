"""Tests that the service API's README says what a connected instance does, exactly (ADR 0137)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from azathoth import api
from azathoth.api.connected import CallTransport
from azathoth.remote.refusals import refusal_body
from tests.api.test_call_transport import TOKEN, URL, Fixed, Unreached

ROOT = Path(__file__).parents[2]

API = ROOT / "src" / "azathoth" / "api" / "README.md"

REMOTE = ROOT / "src" / "azathoth" / "remote" / "README.md"

ERROR_ROW = re.compile(r"^\| `(\w+Error)` \| `(\w+)` \|", re.MULTILINE)


def documented(
    readme: Path,
    message: str,
) -> None:
    """Require a README to quote one message, as a line of its own."""

    assert f"\n{message}\n" in readme.read_text(encoding="utf-8")


def refused(
    http: Fixed,
    call: str = "describe",
) -> str:
    """Return what sending one call over an HTTP client raises, as the README quotes it."""

    with pytest.raises(api.ApiError) as caught:
        CallTransport(URL, TOKEN, http=http).call(call, {})

    return str(caught.value).replace(URL, "<URL>").replace(call, "<CALL>")


def test_the_errors_table_names_every_error_with_its_code() -> None:
    errors = {
        kind.__name__: kind.code
        for name in api.__all__
        if isinstance(kind := getattr(api, name), type)
        and issubclass(kind, api.ApiError)
        and kind is not api.ApiError
    }
    section = API.read_text(encoding="utf-8").split("\n## Errors\n", 1)[1].split("\n## ")[0]

    assert dict(ERROR_ROW.findall(section)) == errors


def test_a_jobs_refusal_is_documented() -> None:
    with api.connect(URL, token=TOKEN, http=Fixed(200, b"{}")) as instance:
        run: Any = instance.runs.run

        with pytest.raises(api.RemoteRefusedError) as caught:
            run()

    documented(API, str(caught.value).replace("runs.run", "<CALL>"))


def test_a_remote_not_reached_is_documented() -> None:
    message = refused(Unreached())

    documented(API, message.replace("Connection refused", "<REASON>"))


def test_a_server_that_is_no_remote_is_documented() -> None:
    documented(API, refused(Fixed(404, b"Not Found")))
    documented(API, refused(Fixed(502, b"<html>Bad gateway</html>")).replace("502", "<STATUS>"))
    documented(API, refused(Fixed(200, b'{"not": "a description"}')))


def test_the_refusal_the_remote_readme_shows_is_one_a_remote_sends() -> None:
    shown = json.dumps(
        refusal_body(api.RevisionNotFoundError("Workflow <ID> has no revision 3.")),
    )

    assert f"\n{shown}\n" in REMOTE.read_text(encoding="utf-8")
