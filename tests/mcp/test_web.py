"""Tests for serving over Streamable HTTP, with and without authorization (ADR 0111).

The servers here are real: uvicorn serves each on a free loopback port in a
thread, and the SDK's client reaches it over HTTP. The identity provider is
a key generated for the test, whose published keys a second local server
serves.
"""

import asyncio
import contextlib
import json
import logging
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx2
import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette

from azathoth.persistence.repositories import open_repositories
from azathoth.prompting import FixedModelSelection, PromptStrategySpec
from azathoth.providers import Prompt
from azathoth.strategies import StrategyMetadata
from azathoth.workflows import (
    WorkflowMetadata,
    WorkflowProductionState,
    WorkflowSpecification,
    WorkflowStepSpecification,
)
from azathoth_mcp.access import STDIO_CALLER
from azathoth_mcp.authorization import AuthorizationSettings
from azathoth_mcp.catalog import ToolCatalog
from azathoth_mcp.cli import http_application
from azathoth_mcp.exposure import ExposedWorkflow, ExposureDocument
from azathoth_mcp.server import build_server
from azathoth_mcp.service import ToolService
from azathoth_mcp.web import (
    LOOPBACK_HOSTS,
    LOOPBACK_ORIGINS,
    UnprotectedBindError,
    http_app,
    is_loopback,
    require_protection,
    scopes_supported,
    transport_security,
)
from tests.mcp.test_service import instance_serving

SUMMARIZE_ID = UUID("7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44")

TRIAGE_ID = UUID("0c9e6a52-5d1b-4f7e-8a3c-91b2d4e6f708")

PRIMARY = FixedModelSelection(provider="test-provider", model="production-model")

ISSUER = "https://idp.example.com/tenant"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

EXPOSURE = ExposureDocument(
    version=1,
    tools=(
        ExposedWorkflow(workflow_id=SUMMARIZE_ID, name="summarize", description="Summarize."),
        ExposedWorkflow(workflow_id=TRIAGE_ID, name="triage", description="Triage."),
    ),
)


def free_port() -> int:
    """Return a loopback port nothing listens on."""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))

        return int(probe.getsockname()[1])


def production_state(
    workflow_id: UUID,
) -> WorkflowProductionState:
    """Return a one-step production state of one workflow, on the fake model."""

    return WorkflowProductionState(
        specification=WorkflowSpecification(
            metadata=WorkflowMetadata(
                id=workflow_id,
                name=f"workflow-{workflow_id}",
                description="Exercise HTTP.",
            ),
            steps=(
                WorkflowStepSpecification(
                    id=UUID(int=1),
                    specification=PromptStrategySpec(
                        metadata=StrategyMetadata(
                            id=UUID(int=2), name="http-step", description="Exercise HTTP."
                        ),
                        prompt=Prompt(text="Summarize."),
                        model_selection=PRIMARY,
                    ),
                ),
            ),
        ),
    )


def service_over(
    tmp_path: Path,
) -> ToolService:
    """Return a tool service over a fresh database with both workflows active."""

    database = tmp_path / "azathoth.db"
    stores = open_repositories(database)

    for workflow_id in (SUMMARIZE_ID, TRIAGE_ID):
        stores.production_states.set(production_state(workflow_id))

    return ToolService(
        catalog=ToolCatalog(EXPOSURE, stores.production_states),
        instance=instance_serving(database, PRIMARY),
    )


@contextlib.contextmanager
def serving(
    application: Starlette,
    port: int,
) -> Iterator[str]:
    """Serve one application on a loopback port in a thread, yielding its base URL."""

    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_config=None, lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30

    while not server.started:
        assert time.monotonic() < deadline, "The server did not start."
        time.sleep(0.02)

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)


@contextlib.contextmanager
def publishing_keys() -> Iterator[str]:
    """Serve the test provider's published keys, yielding their URL."""

    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
    document = json.dumps({"keys": [{**public, "kid": "k1"}]}).encode("utf-8")

    class Keys(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, format: str, *args: Any) -> None:
            return None

    keys = ThreadingHTTPServer(("127.0.0.1", 0), Keys)
    thread = threading.Thread(target=keys.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{keys.server_address[1]}/keys"
    finally:
        keys.shutdown()
        thread.join(timeout=30)


def bearer(
    resource: str,
    *,
    scope: str,
    subject: str = "alice",
    audience: str | None = None,
) -> str:
    """Return a token from the test provider."""

    now = int(time.time())

    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": audience or resource,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "scope": scope,
            "azp": "claude-desktop",
        },
        KEY,
        algorithm="RS256",
        headers={"kid": "k1"},
    )


def session(
    url: str,
    work: Any,
    *,
    token: str | None = None,
) -> Any:
    """Connect a client to a server, with a token if given, and do some work with it."""

    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}

    async def run() -> Any:
        async with (
            httpx2.AsyncClient(headers=headers) as http,
            Client(streamable_http_client(url, http_client=http)) as client,
        ):
            return await work(client)

    return asyncio.run(run())


async def tool_names(
    client: Client,
) -> list[str]:
    """Return the names of the tools a client is offered."""

    return [tool.name for tool in (await client.list_tools()).tools]


# Binding and checks


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "[::1]", "127.0.0.2"])
def test_loopback_addresses_are_loopback(
    host: str,
) -> None:
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.5", "localhost", "example.com"])
def test_anything_else_is_not(
    host: str,
) -> None:
    assert not is_loopback(host)


def test_a_server_without_authorization_refuses_to_listen_beyond_loopback() -> None:
    require_protection("127.0.0.1", None)

    with pytest.raises(UnprotectedBindError) as raised:
        require_protection("0.0.0.0", None)

    assert str(raised.value) == (
        "Without --issuer and --resource, the server authorizes no one, so it listens "
        "only on a loopback address, such as 127.0.0.1 or ::1; got --host 0.0.0.0."
    )


def test_a_server_with_authorization_may_listen_anywhere() -> None:
    require_protection("0.0.0.0", AuthorizationSettings(issuer=ISSUER, resource="https://m/mcp"))


def test_a_server_without_authorization_answers_loopback_names() -> None:
    security = transport_security(None, allowed_origins=["http://tool.local"])

    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == list(LOOPBACK_HOSTS)
    assert security.allowed_origins == [*LOOPBACK_ORIGINS, "http://tool.local"]


def test_a_server_with_authorization_answers_its_resources_host_and_any_added() -> None:
    security = transport_security(
        AuthorizationSettings(issuer=ISSUER, resource="https://mcp.example.com:8443/mcp"),
        allowed_hosts=["10.0.0.5:8000"],
    )

    assert security.allowed_hosts == ["mcp.example.com:8443", "10.0.0.5:8000"]
    assert security.allowed_origins == []


def test_the_metadata_advertises_every_scope_a_tool_needs(
    tmp_path: Path,
) -> None:
    assert scopes_supported(service_over(tmp_path).catalog) == [
        "azathoth:invoke:summarize",
        "azathoth:invoke:triage",
        "azathoth:read",
        "azathoth:read:all",
    ]


def test_authorization_and_a_verifier_come_together(
    tmp_path: Path,
) -> None:
    service = service_over(tmp_path)

    with pytest.raises(ValueError) as raised:
        http_app(
            build_server(service, caller_of=lambda: STDIO_CALLER),
            service.catalog,
            authorization=AuthorizationSettings(issuer=ISSUER, resource="https://m/mcp"),
            verifier=None,
        )

    assert str(raised.value) == (
        "Authorization and a token verifier are given together, or neither."
    )


# Without authorization


def test_a_loopback_server_serves_whoever_connects(
    tmp_path: Path,
) -> None:
    service = service_over(tmp_path)
    port = free_port()

    async def work(client: Client) -> tuple[list[str], Any]:
        names = await tool_names(client)
        result = await client.call_tool("summarize", {"input": "x", "idempotency_key": "k-1"})

        return names, result.structured_content

    with serving(http_application(service, None), port) as base:
        names, outcome = session(f"{base}/mcp", work)

    assert names == ["summarize", "triage", "get_invocation"]
    assert outcome["status"] == "succeeded"

    stores = open_repositories(tmp_path / "azathoth.db")
    invocation = stores.invocations.invocation_for_idempotency_key("k-1")

    assert invocation is not None
    assert invocation.caller_metadata == {"mcp": {"transport": "http", "tool": "summarize"}}


def test_every_request_is_served_on_its_own_without_a_session(
    tmp_path: Path,
) -> None:
    port = free_port()
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }

    with serving(http_application(service_over(tmp_path), None), port) as base:
        response = httpx2.post(
            f"{base}/mcp",
            json=initialize,
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 200
    assert "mcp-session-id" not in response.headers


def test_a_loopback_server_refuses_a_foreign_host_and_origin(
    tmp_path: Path,
) -> None:
    port = free_port()

    with serving(http_application(service_over(tmp_path), None), port) as base:
        foreign_host = httpx2.post(f"{base}/mcp", json={}, headers={"Host": "attacker.example.com"})
        foreign_origin = httpx2.post(
            f"{base}/mcp", json={}, headers={"Origin": "https://attacker.example.com"}
        )

    assert foreign_host.status_code == 421
    assert foreign_origin.status_code == 403


# With authorization


def authorized(
    tmp_path: Path,
    port: int,
    jwks_url: str,
) -> tuple[Starlette, str]:
    """Return an authorizing application for a server on one port, and its resource URL."""

    resource = f"http://127.0.0.1:{port}/mcp"
    application = http_application(
        service_over(tmp_path),
        AuthorizationSettings(issuer=ISSUER, resource=resource, jwks_url=jwks_url),
    )

    return application, resource


def test_a_request_without_a_token_is_pointed_to_the_metadata(
    tmp_path: Path,
) -> None:
    port = free_port()

    with publishing_keys() as jwks_url:
        application, resource = authorized(tmp_path, port, jwks_url)

        with serving(application, port) as base:
            refused = httpx2.post(resource, json={})
            metadata = httpx2.get(f"{base}/.well-known/oauth-protected-resource/mcp")

    assert refused.status_code == 401
    assert refused.headers["www-authenticate"] == (
        'Bearer error="invalid_token", error_description="Authentication required", '
        f'resource_metadata="{base}/.well-known/oauth-protected-resource/mcp"'
    )
    assert metadata.status_code == 200
    assert metadata.json() == {
        "resource": resource,
        "authorization_servers": [ISSUER],
        "scopes_supported": [
            "azathoth:invoke:summarize",
            "azathoth:invoke:triage",
            "azathoth:read",
            "azathoth:read:all",
        ],
        "bearer_methods_supported": ["header"],
        "resource_name": "Azathoth",
    }


@pytest.mark.parametrize(
    "token_for",
    [
        lambda resource: bearer(resource, scope="azathoth:read", audience="https://other/mcp"),
        lambda resource: "not-a-token",
        lambda resource: bearer(resource, scope="azathoth:read") + "x",
    ],
    ids=["another-audience", "garbage", "bad-signature"],
)
def test_a_token_the_server_does_not_accept_is_refused(
    tmp_path: Path,
    token_for: Any,
) -> None:
    port = free_port()

    with publishing_keys() as jwks_url:
        application, resource = authorized(tmp_path, port, jwks_url)

        with serving(application, port):
            refused = httpx2.post(
                resource, json={}, headers={"Authorization": f"Bearer {token_for(resource)}"}
            )

    assert refused.status_code == 401


def test_a_caller_is_served_what_its_token_allows_and_recorded(
    tmp_path: Path,
) -> None:
    port = free_port()

    async def work(client: Client) -> tuple[list[str], Any, Any]:
        names = await tool_names(client)
        made = await client.call_tool("summarize", {"input": "x", "idempotency_key": "alice-1"})
        refused = await client.call_tool("triage", {"input": "x"})

        return names, made.structured_content, refused

    with publishing_keys() as jwks_url:
        application, resource = authorized(tmp_path, port, jwks_url)

        with serving(application, port):
            names, outcome, refused = session(
                resource,
                work,
                token=bearer(resource, scope="azathoth:invoke:summarize azathoth:read"),
            )

    assert names == ["summarize", "get_invocation"]
    assert outcome["status"] == "succeeded"
    assert refused.is_error is True
    assert refused.content[0].text == 'This call needs the scope "azathoth:invoke:triage".'

    invocation = open_repositories(
        tmp_path / "azathoth.db"
    ).invocations.invocation_for_idempotency_key("alice-1")

    assert invocation is not None
    assert invocation.caller_metadata == {
        "mcp": {
            "transport": "http",
            "tool": "summarize",
            "subject": "alice",
            "client_id": "claude-desktop",
        }
    }


def test_each_request_is_served_under_its_own_token(
    tmp_path: Path,
) -> None:
    port = free_port()

    async def made(client: Client) -> Any:
        result = await client.call_tool("summarize", {"input": "x"})

        return result.structured_content

    async def read_by(client: Client, invocation_id: str) -> Any:
        return await client.call_tool("get_invocation", {"invocation_id": invocation_id})

    scope = "azathoth:invoke:summarize azathoth:read"

    with publishing_keys() as jwks_url:
        application, resource = authorized(tmp_path, port, jwks_url)

        with serving(application, port):
            alices = session(resource, made, token=bearer(resource, scope=scope))
            invocation_id = alices["invocation_id"]

            by_alice = session(
                resource,
                lambda client: read_by(client, invocation_id),
                token=bearer(resource, scope=scope),
            )
            by_bob = session(
                resource,
                lambda client: read_by(client, invocation_id),
                token=bearer(resource, scope=scope, subject="bob"),
            )

    assert by_alice.is_error is False
    assert by_bob.is_error is True
    assert by_bob.content[0].text == f"No invocation {invocation_id} was found."


def test_no_token_is_ever_logged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    port = free_port()

    async def work(client: Client) -> None:
        await client.list_tools()
        await client.call_tool("summarize", {"input": "x"})

    with publishing_keys() as jwks_url:
        application, resource = authorized(tmp_path, port, jwks_url)
        accepted = bearer(resource, scope="azathoth:invoke:summarize")
        refused = bearer(resource, scope="azathoth:read", audience="https://other/mcp")

        with caplog.at_level(logging.DEBUG), serving(application, port):
            session(resource, work, token=accepted)
            httpx2.post(resource, json={}, headers={"Authorization": f"Bearer {refused}"})

    assert caplog.records

    for raw in (accepted, refused):
        for part in raw.split("."):
            assert part not in caplog.text
