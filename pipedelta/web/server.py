"""The web server: a JSON API plus the static front end. Standard library only.

Security choices (each has a test in tests/test_web_api.py):

* binds to 127.0.0.1 by default;
* the ``Host`` header must be a local name, which stops DNS-rebinding pages;
* a write must be ``application/json`` and, if it names an ``Origin``, the
  same origin as the page, which stops other websites from posting to it;
* the GitHub token is read from the server's environment and never appears in
  any response;
* request bodies are capped; paths are checked before they reach GitHub;
* every error is JSON ``{"error": {"code", "message"}}`` and never a traceback;
* static files are served only from the ``static`` folder.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from . import reports
from .github_client import GitHub, GitHubError, parse_repository, token_from_environment
from .incidents import incident_list, load_incident
from .samples import load_sample, sample_list
from .service import AnalysisService, InputError
from .store import Store

STATIC = Path(__file__).parent / "static"
MAX_BODY = 600 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
}

_ANALYSIS_ID = re.compile(r"^[0-9a-f]{12}$")


class HttpError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail or {}


def make_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str = ":memory:",
    github: GitHub | None = None,
    extra_hosts: set[str] | None = None,
) -> ThreadingHTTPServer:
    """Build the server. Tests pass their own ``github`` and ``:memory:``."""
    store = Store(db_path)
    client = github or GitHub(token_from_environment())
    service = AnalysisService(client, store)
    allowed = LOCAL_HOSTS | (extra_hosts or set())

    class Handler(BaseHTTPRequestHandler):
        server_version = f"PipeDelta/{__version__}"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # one quiet line, no query strings
            sys.stderr.write(
                f"[{self.log_date_time_string()}] {self.command} {self.path.split('?')[0]}\n"
            )

        # -- plumbing --

        def _send(
            self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _error(
            self, status: int, code: str, message: str, detail: dict[str, Any] | None = None
        ) -> None:
            self._json(
                status, {"error": {"code": code, "message": message, "detail": detail or {}}}
            )

        def _check_host(self) -> None:
            header = (self.headers.get("Host") or "").lower()
            host = header.split("]")[0] + "]" if header.startswith("[") else header.split(":")[0]
            if host not in allowed:
                raise HttpError(403, "bad_host", "This server only answers to localhost.")

        def _check_write(self) -> None:
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                raise HttpError(403, "bad_origin", "Requests from other websites are refused.")
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise HttpError(
                    415, "bad_content_type", "Send JSON with Content-Type: application/json."
                )

        def _body(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise HttpError(400, "bad_length", "The request length is not valid.") from None
            if length > MAX_BODY:
                # Read and drop what was sent so the browser sees our answer, not a reset.
                self.rfile.read(min(length, 8 * 1024 * 1024))
                raise HttpError(413, "too_large", "The request is larger than 600 KB.")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                raise HttpError(400, "bad_json", "The request body is not valid JSON.") from None
            if not isinstance(data, dict):
                raise HttpError(400, "bad_json", "The request body must be a JSON object.")
            return data

        # -- dispatch --

        def _handle(self, method: str) -> None:
            try:
                self._check_host()
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if method in ("POST", "DELETE"):
                    self._check_write()
                if path.startswith("/api/"):
                    body = self._body() if method == "POST" else {}
                    self._api(method, path[4:], query, body)
                elif method in ("GET", "HEAD"):
                    self._static(path)
                else:
                    raise HttpError(405, "method_not_allowed", "That method is not allowed here.")
            except HttpError as error:
                self._error(error.status, error.code, error.message, error.detail)
            except InputError as error:
                self._error(error.status, error.code, error.message)
            except GitHubError as error:
                self._error(error.status, error.code, error.message, error.detail)
            except Exception:  # noqa: BLE001  # a bug: log it for the developer, tell the user plainly
                traceback.print_exc(file=sys.stderr)
                self._error(
                    500, "internal", "Something went wrong inside PipeDelta. See the server log."
                )

        def do_GET(self) -> None:
            self._handle("GET")

        def do_HEAD(self) -> None:
            self._handle("HEAD")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_DELETE(self) -> None:
            self._handle("DELETE")

        # -- the API --

        def _api(self, method: str, path: str, query: dict[str, str], body: dict[str, Any]) -> None:
            route = (method, path.rstrip("/") or "/")

            if route == ("GET", "/health"):
                return self._json(200, {"ok": True, "version": __version__})

            if route == ("GET", "/session"):
                rate: dict[str, Any] | None = None
                user: str | None = None
                try:
                    rate = client.rate_limit()
                    user = client.user()
                except GitHubError as error:
                    rate = {"error": error.code}
                return self._json(
                    200,
                    {
                        "version": __version__,
                        "github": {"token_set": client.authenticated, "user": user, "rate": rate},
                    },
                )

            if route == ("GET", "/stats"):
                return self._json(200, store.stats())

            if route == ("GET", "/repos"):
                return self._json(200, {"repos": store.repos()})

            if route == ("POST", "/repos"):
                return self._json(200, service.connect(str(body.get("repo", ""))))

            match = re.fullmatch(r"/repos/([^/]+)/([^/]+)", route[1])
            if match and method == "DELETE":
                full = "/".join(parse_repository(f"{match[1]}/{match[2]}"))
                if not store.remove_repo(full):
                    raise HttpError(404, "not_found", "That repository is not connected.")
                return self._json(200, {"removed": full})

            match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/(workflows|history|pulls)", route[1])
            if match and method == "GET":
                full = f"{match[1]}/{match[2]}"
                if match[3] == "workflows":
                    return self._json(200, service.workflows(full, query.get("ref")))
                if match[3] == "history":
                    commits = service.file_history(full, query.get("path", ""), query.get("ref"))
                    return self._json(200, {"commits": commits})
                return self._json(200, {"pulls": service.pulls(full)})

            if route == ("GET", "/samples"):
                return self._json(200, {"samples": sample_list()})

            if route == ("GET", "/incidents"):
                return self._json(200, {"incidents": incident_list()})

            if route == ("POST", "/analyses"):
                return self._json(200, self._create_analysis(body))

            if route == ("GET", "/analyses"):
                limit = int(query["limit"]) if query.get("limit", "").isdigit() else 100
                return self._json(200, {"analyses": store.analyses(query.get("repo"), limit)})

            match = re.fullmatch(r"/analyses/([^/]+)(?:/(report))?", route[1])
            if match:
                if not _ANALYSIS_ID.match(match[1]):
                    raise HttpError(404, "not_found", "No such analysis.")
                analysis = store.analysis(match[1])
                if analysis is None:
                    raise HttpError(404, "not_found", "No such analysis.")
                if method == "DELETE" and not match[2]:
                    store.remove_analysis(match[1])
                    return self._json(200, {"removed": match[1]})
                if method == "GET" and match[2]:
                    fmt = query.get("format", "md")
                    if fmt not in reports.CONTENT_TYPES:
                        raise HttpError(
                            400, "bad_format", "Format must be md, html, json or sarif."
                        )
                    text = reports.render(analysis, fmt)
                    return self._send(
                        200,
                        text.encode(),
                        reports.CONTENT_TYPES[fmt],
                        {
                            "Content-Disposition": f'attachment; filename="{reports.filename(analysis, fmt)}"'
                        },
                    )
                if method == "GET":
                    return self._json(200, analysis)

            raise HttpError(404, "not_found", "No such endpoint.")

        def _create_analysis(self, body: dict[str, Any]) -> dict[str, Any]:
            kind = body.get("mode")
            if kind == "inventory":
                return service.inventory(
                    str(body.get("repo", "")), str(body.get("path", "")), body.get("ref")
                )
            if kind == "compare":
                return service.compare(
                    str(body.get("repo", "")),
                    str(body.get("path", "")),
                    body.get("base"),
                    body.get("head"),
                    body.get("ref"),
                )
            if kind == "pull":
                number = body.get("number")
                if not isinstance(number, int) or number < 1:
                    raise InputError("bad_number", "Enter a pull request number.")
                return service.pull_request(str(body.get("repo", "")), number)
            if kind == "paste":
                after = body.get("after")
                if not isinstance(after, str) or not after.strip():
                    raise InputError("empty", "Paste the workflow to analyse.")
                before = body.get("before")
                return service.pasted(
                    str(body.get("name") or "pasted-workflow.yml"),
                    before if isinstance(before, str) and before.strip() else None,
                    after,
                )
            if kind == "sample":
                sample = load_sample(str(body.get("sample", "")))
                if sample is None:
                    raise InputError("no_sample", "No such sample.", 404)
                return service.pasted(sample["name"], sample["before"], sample["after"], "sample")
            if kind == "incident":
                case = load_incident(str(body.get("incident", "")))
                if case is None:
                    raise InputError("no_incident", "No such incident.", 404)
                return service.pasted(case["name"], case["before"], case["after"], "incident")
            raise InputError(
                "bad_mode", "mode must be inventory, compare, pull, paste, sample or incident."
            )

        # -- static files --

        def _static(self, path: str) -> None:
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC / name).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                # Unknown paths fall back to the app so a reload on a client route works.
                if "." not in name.rsplit("/", 1)[-1]:
                    target = STATIC / "index.html"
                else:
                    raise HttpError(404, "not_found", "No such file.")
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                kind += "; charset=utf-8"
            self._send(200, target.read_bytes(), kind)

    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str, port: int, db_path: str) -> int:
    server = make_server(host, port, db_path)
    where = f"http://{host}:{server.server_address[1]}"
    token = (
        "set"
        if token_from_environment()
        else "not set (public repositories only, 60 requests/hour)"
    )
    print(f"PipeDelta {__version__} is running at {where}")
    print(f"GitHub token: {token}.  History: {db_path}.  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
