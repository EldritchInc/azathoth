"""The HTTP client a local instance reaches a remote with (ADR 0124).

A `RemoteClient` speaks the protocol `azathoth.remote.server` serves, over
httpx, and turns each refusal into an error whose message is the remote's
own. It is a context manager: a client it opened itself is closed on exit.
"""

from types import TracebackType
from typing import Any, Final, Protocol, TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from azathoth.remote.protocol import SENSITIVITY_HEADER, Capabilities
from azathoth.remote.receiving import ReceiveReport
from azathoth.remote.records import (
    CredentialsRequest,
    CredentialsResponse,
    HeadsRequest,
    HeadsResponse,
    MissingRequest,
    MissingResponse,
    PortfolioResponse,
    PullRequest,
    PullResponse,
    PushBundle,
)
from azathoth.sensitivity import Sensitivity

REMOTE_TOKEN_VARIABLE: Final = "AZATHOTH_REMOTE_TOKEN"
"""The environment variable a remote's token is read from, so no command line holds it."""

DEFAULT_TIMEOUT_SECONDS: Final = 60.0
"""How long one request to a remote may take, in seconds."""

Model = TypeVar("Model", bound=BaseModel)


class HttpResponse(Protocol):
    """An HTTP answer, as a client reads one."""

    @property
    def status_code(
        self,
    ) -> int:
        """Return the answer's status."""

        ...

    @property
    def content(
        self,
    ) -> bytes:
        """Return the answer's body."""

        ...

    @property
    def is_success(
        self,
    ) -> bool:
        """Return whether the status is a success."""

        ...

    def json(
        self,
    ) -> Any:
        """Return the body read as JSON."""

        ...


class HttpClient(Protocol):
    """What a client sends requests over: an httpx client, or a test's in-process one."""

    def request(
        self,
        method: str,
        url: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """Send one request, and return its answer."""

        ...

    def close(
        self,
    ) -> None:
        """Release what the client holds."""

        ...


class RemoteError(Exception):
    """A remote could not be reached, or refused a request; the message says which, and why.

    `status` is the HTTP status of a refusal, or None when the remote was
    not reached or did not answer as a remote does.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status


class RemoteUnreachableError(RemoteError):
    """The remote was not reached, or answered as no remote does."""


class RemoteRefusedError(RemoteError):
    """The remote refused a request: its token, its policy, its checks or its limits."""


class RemoteDivergedError(RemoteRefusedError):
    """The remote refused a push whose lineage has diverged there; pull first."""


class RemoteNotFoundError(RemoteRefusedError):
    """The remote does not hold the content asked for."""


def require_remote_url(
    url: str,
) -> str:
    """Return a remote's URL without a trailing slash, or refuse one that is not http or https.

    Raises:
        ValueError: The URL is not an http or https URL with a host.
    """

    parts = urlsplit(url)

    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"Remote URL {url!r} is not an http or https URL.")

    return url.rstrip("/")


class RemoteClient:
    """One remote, reached with one token."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        http: HttpClient | None = None,
    ) -> None:
        """Reach the remote at `url` with `token`, over `http` when given, as tests do.

        Raises:
            ValueError: The URL is not an http or https URL.
        """

        self.url = require_remote_url(url)
        self._token = token
        self._owned = http is None
        self._http: HttpClient = (
            http
            if http is not None
            else httpx.Client(base_url=self.url, timeout=DEFAULT_TIMEOUT_SECONDS)
        )

    def __enter__(
        self,
    ) -> "RemoteClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(
        self,
    ) -> None:
        """Close the HTTP client, if this client opened it."""

        if self._owned:
            self._http.close()

    def capabilities(
        self,
    ) -> Capabilities:
        """Return what the remote says it is, before anything is sent to it."""

        return self._model(Capabilities, self._request("GET", "/v1/capabilities"))

    def missing(
        self,
        request: MissingRequest,
    ) -> MissingResponse:
        """Return which offered revisions and content the remote lacks."""

        return self._model(
            MissingResponse,
            self._request("POST", "/v1/missing", content=request.model_dump_json()),
        )

    def put_content(
        self,
        digest: str,
        data: bytes,
        *,
        sensitivity: Sensitivity,
    ) -> None:
        """Send one blob of content, labelled as the most sensitive case that holds it."""

        self._request(
            "PUT",
            f"/v1/content/{digest}",
            content=data,
            headers={SENSITIVITY_HEADER: sensitivity.value},
        )

    def get_content(
        self,
        digest: str,
    ) -> bytes:
        """Return one blob of content the remote holds."""

        return self._request("GET", f"/v1/content/{digest}").content

    def push(
        self,
        bundle: PushBundle,
    ) -> ReceiveReport:
        """Send a bundle, and return what the remote received of it."""

        return self._model(
            ReceiveReport,
            self._request("POST", "/v1/push", content=bundle.model_dump_json()),
        )

    def pull(
        self,
        request: PullRequest,
    ) -> PullResponse:
        """Return the bundle the remote sends for a pull."""

        return self._model(
            PullResponse,
            self._request("POST", "/v1/pull", content=request.model_dump_json()),
        )

    def heads(
        self,
        request: HeadsRequest,
    ) -> HeadsResponse:
        """Return the head of each lineage asked about that the remote holds, or of every one."""

        return self._model(
            HeadsResponse,
            self._request("POST", "/v1/heads", content=request.model_dump_json()),
        )

    def portfolio(
        self,
    ) -> PortfolioResponse:
        """Return the models the remote's portfolio authorizes, with their data policies."""

        return self._model(PortfolioResponse, self._request("GET", "/v1/portfolio"))

    def missing_credentials(
        self,
        request: CredentialsRequest,
    ) -> CredentialsResponse:
        """Return which of the credential names asked about the remote does not set."""

        return self._model(
            CredentialsResponse,
            self._request("POST", "/v1/credentials", content=request.model_dump_json()),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """Send one request with the token, and return its answer, or raise the remote's refusal.

        Raises:
            RemoteUnreachableError: The remote was not reached.
            RemoteRefusedError: The remote refused the request.
        """

        try:
            response = self._http.request(
                method,
                path,
                content=content,
                headers={"Authorization": f"Bearer {self._token}", **(headers or {})},
            )
        except httpx.HTTPError as exc:
            raise RemoteUnreachableError(
                f"The remote at {self.url} could not be reached: {exc}"
            ) from exc

        if response.is_success:
            return response

        raise self._refusal(response)

    def _refusal(
        self,
        response: HttpResponse,
    ) -> RemoteError:
        """Return the error a refusal is, with the remote's own message."""

        try:
            body = response.json()
        except ValueError:
            body = None

        message = body.get("error") if isinstance(body, dict) else None

        if not isinstance(message, str):
            return RemoteUnreachableError(
                f"The remote at {self.url} answered {response.status_code} without saying why; "
                "it may not be an Azathoth remote.",
                status=response.status_code,
            )

        kind: type[RemoteError] = {
            httpx.codes.CONFLICT: RemoteDivergedError,
            httpx.codes.NOT_FOUND: RemoteNotFoundError,
        }.get(httpx.codes(response.status_code), RemoteRefusedError)

        return kind(message, status=response.status_code)

    def _model(
        self,
        model: type[Model],
        response: HttpResponse,
    ) -> Model:
        """Return an answer read as one protocol model.

        Raises:
            RemoteUnreachableError: The answer is not that model's JSON.
        """

        try:
            return model.model_validate_json(response.content)
        except ValidationError:
            raise RemoteUnreachableError(
                f"The remote at {self.url} answered with something other than a "
                f"{model.__name__}; it may not be an Azathoth remote, or not of this protocol.",
                status=response.status_code,
            ) from None


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "REMOTE_TOKEN_VARIABLE",
    "HttpClient",
    "HttpResponse",
    "RemoteClient",
    "RemoteDivergedError",
    "RemoteError",
    "RemoteNotFoundError",
    "RemoteRefusedError",
    "RemoteUnreachableError",
    "require_remote_url",
]
