"""The service API of a remote, called over HTTP as a local instance is called (ADR 0137).

A `CallTransport` sends one call of the service API to a remote, as `POST
/v1/calls/<name>` with the call's arguments by name, and returns its result
as the call returns it locally: `azathoth.remote.calling` writes the
arguments and reads the result from the call's own method, as the remote
does. A refusal is raised as the error a local instance would have raised,
with the remote's message (`azathoth.remote.refusals`).
"""

from collections.abc import Mapping
from http import HTTPStatus
from types import TracebackType
from typing import Any, Final

import httpx
from pydantic import ValidationError

from azathoth.api.errors import RemoteUnreachableError
from azathoth.remote.calling import CALLS_ROUTE, call_signature
from azathoth.remote.client import DEFAULT_TIMEOUT_SECONDS, HttpClient, require_remote_url
from azathoth.remote.refusals import Refusal, api_error

JSON_MEDIA_TYPE: Final = "application/json"
"""The media type of a call's arguments, and of its result."""


class CallTransport:
    """Calls of the service API, sent to one remote with one token."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        http: HttpClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Reach the remote at `url` with `token`, over `http` when given, as tests do.

        Without `http`, each call may take `timeout` seconds.

        Raises:
            ValueError: The URL is not an http or https URL.
        """

        self.url = require_remote_url(url)
        self._token = token
        self._owned = http is None
        self._http: HttpClient = (
            http if http is not None else httpx.Client(base_url=self.url, timeout=timeout)
        )

    def __enter__(
        self,
    ) -> "CallTransport":
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
        """Close the HTTP client, if this transport opened it."""

        if self._owned:
            self._http.close()

    def call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Send one call with the arguments given by name, and return its result.

        Only the arguments given are sent, so those left out take the
        call's defaults at the remote.

        Raises:
            CallArgumentsError: The arguments are not the call's; nothing
                was sent.
            NotServedError: A remote never serves the call, or runs it as a
                job; nothing was sent.
            LookupError: The service API has no call of the name.
            RemoteUnreachableError: The remote was not reached, or answered
                as no remote serving the service API does.
            ApiError: The remote refused the call: the error a local
                instance would have raised, of the nearest kind this
                Azathoth knows, or a `RemoteRefusedError`.
        """

        signature = call_signature(name)
        body = signature.write_arguments(**arguments)

        try:
            response = self._http.request(
                "POST",
                CALLS_ROUTE.format(name=name),
                content=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": JSON_MEDIA_TYPE,
                },
            )
        except httpx.HTTPError as exc:
            raise RemoteUnreachableError(
                f"The remote at {self.url} could not be reached: {exc}"
            ) from exc

        if not response.is_success:
            raise self._refused(name, response.status_code, response.content)

        try:
            return signature.read_result(response.content)
        except ValidationError:
            raise RemoteUnreachableError(
                f"The remote at {self.url} answered {name} with something other than its "
                "result; it may serve another version of the service API."
            ) from None

    def _refused(
        self,
        name: str,
        status: int,
        body: bytes,
    ) -> Exception:
        """Return the error a refusal is, or say the remote answered as none serving calls does."""

        try:
            refused = Refusal.model_validate_json(body)
        except ValidationError:
            refused = None

        if refused is not None:
            return api_error(status, refused)

        if status == HTTPStatus.NOT_FOUND:
            return RemoteUnreachableError(
                f"The remote at {self.url} does not serve {name}; it may not serve the service "
                "API, which a remote does from Azathoth 1.6."
            )

        return RemoteUnreachableError(
            f"The remote at {self.url} answered {name} with {status} without saying why; it may "
            "not be an Azathoth remote."
        )


__all__ = [
    "JSON_MEDIA_TYPE",
    "CallTransport",
]
