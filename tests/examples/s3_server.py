"""A stand-in for S3 over HTTP, for running the S3 tools in real processes (ADR 0110).

It serves path-style requests, `/<BUCKET>/<KEY>`, for the calls the S3 tools
make and nothing more: HEAD, GET with `Range` and `If-Match`, and PUT. It
checks no signature, so any credentials do. Pointing boto3 at it with
`AWS_ENDPOINT_URL_S3` lets a workflow's S3 tools run through Azathoth's own
process runtime, as they run on a worker, without reaching AWS.
"""

import hashlib
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")


@dataclass
class StoredObject:
    """One object: its bytes, ETag and content type."""

    content: bytes
    content_type: str

    @property
    def etag(self) -> str:
        """Return the object's ETag, quoted as S3 quotes it."""

        return f'"{hashlib.md5(self.content).hexdigest()}"'


@dataclass
class S3Objects:
    """The objects the stand-in holds, by bucket and key, and every call it served."""

    objects: dict[tuple[str, str], StoredObject] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def put(
        self,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str = "text/plain",
    ) -> None:
        """Store one object."""

        with self.lock:
            self.objects[(bucket, key)] = StoredObject(content, content_type)

    def keys(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[str]:
        """Return the keys of one bucket under a prefix, in order."""

        with self.lock:
            return sorted(
                key for (name, key) in self.objects if name == bucket and key.startswith(prefix)
            )

    def get(
        self,
        bucket: str,
        key: str,
    ) -> bytes:
        """Return one object's bytes."""

        with self.lock:
            return self.objects[(bucket, key)].content


class _Handler(BaseHTTPRequestHandler):
    """Answers one request against the server's objects."""

    server: "_Server"

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        """Log nothing."""

    def _target(self) -> tuple[str, str]:
        """Return the request's bucket and key."""

        path = unquote(urlsplit(self.path).path).lstrip("/")
        bucket, _, key = path.partition("/")

        return bucket, key

    def _error(
        self,
        status: int,
        code: str,
        message: str,
    ) -> None:
        """Answer with an S3 error document."""

        body = (
            f"<?xml version='1.0' encoding='UTF-8'?><Error><Code>{code}</Code>"
            f"<Message>{message}</Message></Error>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body) if self.command != "HEAD" else 0))
        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(body)

    def _found(self) -> StoredObject | None:
        """Record the call, and return the object it names, if there is one."""

        bucket, key = self._target()
        objects = self.server.objects

        with objects.lock:
            objects.calls.append((self.command, f"{bucket}/{key}"))
            return objects.objects.get((bucket, key))

    def do_HEAD(self) -> None:
        """Answer a HEAD with the object's size, ETag and content type."""

        found = self._found()

        if found is None:
            self._error(404, "404", "Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(found.content)))
        self.send_header("ETag", found.etag)
        self.send_header("Content-Type", found.content_type)
        self.end_headers()

    def do_GET(self) -> None:
        """Answer a GET, honoring `If-Match` and one `bytes=<FIRST>-<LAST>` range."""

        found = self._found()

        if found is None:
            self._error(404, "NoSuchKey", "The specified key does not exist.")
            return

        match = self.headers.get("If-Match")

        if match is not None and match != found.etag:
            self._error(412, "PreconditionFailed", "At least one of the pre-conditions failed.")
            return

        content = found.content
        status = 200
        requested = self.headers.get("Range")

        if requested is not None:
            bounds = RANGE.match(requested)
            assert bounds is not None, requested
            first, last = int(bounds[1]), int(bounds[2])

            if first >= len(content):
                self._error(416, "InvalidRange", "The requested range is not satisfiable")
                return

            content = content[first : last + 1]
            status = 206

        self.send_response(status)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("ETag", found.etag)
        self.send_header("Content-Type", found.content_type)
        self.end_headers()
        self.wfile.write(content)

    def do_PUT(self) -> None:
        """Store the request's body as the object."""

        self._found()
        bucket, key = self._target()
        content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        stored = StoredObject(content, self.headers.get("Content-Type", "binary/octet-stream"))

        with self.server.objects.lock:
            self.server.objects.objects[(bucket, key)] = stored

        self.send_response(200)
        self.send_header("ETag", stored.etag)
        self.send_header("Content-Length", "0")
        self.end_headers()


class _Server(ThreadingHTTPServer):
    """An HTTP server holding the stand-in's objects."""

    daemon_threads = True

    def __init__(
        self,
        objects: S3Objects,
    ) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.objects = objects


@contextmanager
def s3_server() -> Iterator[tuple[str, S3Objects]]:
    """Serve an empty stand-in for S3; yield its endpoint URL and its objects."""

    objects = S3Objects()
    server = _Server(objects)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address[:2]
        yield f"http://{host!s}:{port}", objects
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
