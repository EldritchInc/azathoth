"""Tests that the READMEs say what a remote serves of the service API, exactly (ADR 0136)."""

import re
from pathlib import Path

from starlette.routing import Route

from azathoth.api.calls import SERVICE_CALLS
from azathoth.cli.remote import AUDIT_UNTOLD_MESSAGE, OPERATOR_PREFIX
from azathoth.remote.server import AUDIT_UNAVAILABLE_MESSAGE
from azathoth.remote.service import MAX_PERMISSION_RESOURCES
from tests.remote.test_call_routes import ERIS, Served

ROOT = Path(__file__).parents[2]

REMOTE = ROOT / "src" / "azathoth" / "remote" / "README.md"

CLI = ROOT / "src" / "azathoth" / "cli" / "README.md"

ROUTE_ROW = re.compile(r"^\| `(GET|POST|PUT) (/[^`]*)` \|", re.MULTILINE)

STATUS_ROW = re.compile(r"^\| (\d{3}) \|", re.MULTILINE)


def documented(
    readme: Path,
    message: str,
) -> None:
    """Require a README to quote one message, as a line of its own."""

    assert f"\n{message}\n" in readme.read_text(encoding="utf-8")


def section(
    readme: Path,
    heading: str,
) -> str:
    """Return one `##` section of a README, up to the next."""

    text = readme.read_text(encoding="utf-8")
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)

    return text[start : end if end != -1 else len(text)]


def test_the_route_table_names_every_route_the_server_answers(
    tmp_path: Path,
) -> None:
    app = Served(tmp_path / "azathoth.db", principal=ERIS).app
    served = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, Route)
        for method in route.methods or ()
        if method != "HEAD"
    }

    assert set(ROUTE_ROW.findall(section(REMOTE, "The Server"))) == served


def test_the_refusal_table_names_every_status_a_service_route_answers() -> None:
    statuses = STATUS_ROW.findall(section(REMOTE, "The Server"))

    assert statuses == [
        "400",
        "401",
        "403",
        "404",
        "409",
        "413",
        "422",
        "500",
        "501",
        "502",
        "503",
    ]


def test_a_jobs_refusal_is_documented(
    tmp_path: Path,
) -> None:
    served = Served(tmp_path / "azathoth.db", principal=ERIS, runs_jobs=False)
    (job, *_) = [call.name for call in SERVICE_CALLS if call.job]
    answer = served.call(job)

    documented(REMOTE, answer.json()["error"].replace(job, "<NAME>", 1))


def test_a_protocol_only_remotes_refusal_is_documented(
    tmp_path: Path,
) -> None:
    answer = Served(tmp_path / "azathoth.db", serves_calls=False).call("describe")

    documented(REMOTE, answer.json()["error"])


def test_an_unavailable_audits_refusal_is_documented() -> None:
    documented(REMOTE, AUDIT_UNAVAILABLE_MESSAGE)


def test_the_most_resources_permissions_are_asked_of_is_documented() -> None:
    assert f"up to {MAX_PERMISSION_RESOURCES}\nresources" in REMOTE.read_text(encoding="utf-8")


def test_a_token_commands_audit_is_documented() -> None:
    documented(CLI, AUDIT_UNTOLD_MESSAGE.format(reason="<REASON>"))

    for readme in (REMOTE, CLI):
        assert f"`{OPERATOR_PREFIX}<AUTHOR>`" in readme.read_text(encoding="utf-8")
