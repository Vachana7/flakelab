"""A small, read-only GitHub client for the web app.

Design rules:

* standard library only (urllib), and it talks to ``api.github.com`` only;
* the token comes from the server's environment and is sent only in the
  ``Authorization`` header. It is never returned to the browser, never put in
  a URL and never written into an error message;
* every name that goes into a URL is checked first, so a request cannot be
  steered to another path or host;
* only reads: repository, workflow files, file history, pull requests.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

API = "https://api.github.com"
MAX_FILE_BYTES = 256 * 1024
TIMEOUT_SECONDS = 20
TOKEN_VARIABLES = ("PIPEDELTA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9_. -]{1,100}\.ya?ml$")


class GitHubError(Exception):
    """A problem the user can understand. ``code`` is stable; ``message`` is for people."""

    def __init__(
        self, code: str, message: str, status: int = 502, detail: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}


def token_from_environment(env: dict[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    for name in TOKEN_VARIABLES:
        value = source.get(name, "").strip()
        if value:
            return value
    return None


def parse_repository(text: str) -> tuple[str, str]:
    """``owner/name`` or a github.com URL -> (owner, name). Raises GitHubError."""
    value = (text or "").strip()
    value = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", value)
    value = re.sub(r"\.git$", "", value).strip("/")
    parts = value.split("/")
    if len(parts) < 2 or not _NAME.match(parts[0]) or not _NAME.match(parts[1]):
        raise GitHubError(
            "bad_repository",
            "Enter a repository as owner/name, for example pallets/flask.",
            status=400,
        )
    return parts[0], parts[1]


def check_workflow_path(path: str) -> str:
    if not _WORKFLOW_PATH.match(path or "") or ".." in path:
        raise GitHubError(
            "bad_path",
            "A workflow file must be under .github/workflows/ and end in .yml or .yaml.",
            400,
        )
    return path


def check_ref(ref: str | None) -> str | None:
    if ref in (None, ""):
        return None
    if not (_SHA.match(ref) or _REF.match(ref)) or ".." in ref:
        raise GitHubError("bad_ref", "That branch, tag or commit name is not valid.", 400)
    return ref


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """urllib resends the Authorization header on a redirect. Only follow ones to GitHub's API."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != "https" or parts.hostname != "api.github.com":
            raise GitHubError("bad_redirect", "GitHub tried to send the request elsewhere.", 502)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SameHostRedirects)


class GitHub:
    """Reads from the GitHub REST API. ``opener`` can be replaced in tests."""

    def __init__(
        self,
        token: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._token = token
        self._open = opener or build_opener().open
        self.last_rate: dict[str, int] | None = None

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    # ---- transport ----------------------------------------------------------

    def _get(self, path: str, params: dict[str, str] | None = None, raw: bool = False) -> Any:
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pipedelta-web",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._open(request, timeout=TIMEOUT_SECONDS) as response:
                self._note_rate(response.headers)
                body = response.read(MAX_FILE_BYTES + 1 if raw else 8 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            self._note_rate(error.headers)
            raise self._translate(error) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise GitHubError(
                "network",
                f"Could not reach GitHub ({type(reason).__name__}). Check the internet connection.",
                502,
            ) from None
        if raw:
            if len(body) > MAX_FILE_BYTES:
                raise GitHubError("too_large", "That workflow file is larger than 256 KB.", 413)
            return body.decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except ValueError:
            raise GitHubError(
                "bad_response", "GitHub sent a reply that could not be read.", 502
            ) from None

    def _note_rate(self, headers: Any) -> None:
        try:
            self.last_rate = {
                "limit": int(headers.get("X-RateLimit-Limit", "")),
                "remaining": int(headers.get("X-RateLimit-Remaining", "")),
                "reset": int(headers.get("X-RateLimit-Reset", "0")),
            }
        except (TypeError, ValueError):
            pass

    def _translate(self, error: urllib.error.HTTPError) -> GitHubError:
        remaining = error.headers.get("X-RateLimit-Remaining") if error.headers else None
        if error.code == 401:
            return GitHubError(
                "bad_token", "GitHub did not accept the token set on the server.", 502
            )
        if error.code in (403, 429) and remaining == "0":
            reset = (self.last_rate or {}).get("reset", 0)
            return GitHubError(
                "rate_limited",
                "GitHub's request limit has been reached"
                + ("" if self._token else " (set GITHUB_TOKEN on the server to raise it)")
                + ".",
                429,
                {"reset": reset},
            )
        if error.code == 403:
            return GitHubError("forbidden", "GitHub refused access to that resource.", 403)
        if error.code == 404:
            return GitHubError(
                "not_found",
                "Not found. Check the name, and that the token (if any) can see this repository.",
                404,
            )
        return GitHubError("github_error", f"GitHub answered with an error ({error.code}).", 502)

    # ---- reads --------------------------------------------------------------

    def rate_limit(self) -> dict[str, int]:
        data = self._get("/rate_limit")["resources"]["core"]
        return {"limit": data["limit"], "remaining": data["remaining"], "reset": data["reset"]}

    def user(self) -> str | None:
        if not self._token:
            return None
        try:
            return str(self._get("/user").get("login"))
        except GitHubError:
            return None  # a token that cannot read /user still works for repositories

    def repository(self, owner: str, name: str) -> dict[str, Any]:
        data = self._get(f"/repos/{owner}/{name}")
        return {
            "full_name": data["full_name"],
            "description": data.get("description") or "",
            "private": bool(data.get("private")),
            "default_branch": data.get("default_branch") or "main",
            "html_url": data["html_url"],
            "pushed_at": data.get("pushed_at"),
            "language": data.get("language"),
            "archived": bool(data.get("archived")),
        }

    def workflows(self, owner: str, name: str, ref: str | None) -> list[dict[str, Any]]:
        params = {"ref": ref} if ref else None
        try:
            items = self._get(f"/repos/{owner}/{name}/contents/.github/workflows", params)
        except GitHubError as error:
            if error.code == "not_found":
                return []  # a repository without a workflows folder
            raise
        if not isinstance(items, list):
            return []
        return [
            {
                "path": item["path"],
                "name": item["name"],
                "size": item.get("size", 0),
                "sha": item["sha"],
            }
            for item in items
            if item.get("type") == "file" and str(item.get("name", "")).endswith((".yml", ".yaml"))
        ]

    def file(self, owner: str, name: str, path: str, ref: str | None) -> str:
        params = {"ref": ref} if ref else None
        return str(
            self._get(
                f"/repos/{owner}/{name}/contents/{urllib.parse.quote(path)}", params, raw=True
            )
        )

    def file_commits(
        self, owner: str, name: str, path: str, ref: str | None, limit: int = 20
    ) -> list[dict[str, Any]]:
        params = {"path": path, "per_page": str(limit)}
        if ref:
            params["sha"] = ref
        commits = self._get(f"/repos/{owner}/{name}/commits", params)
        result = []
        for item in commits if isinstance(commits, list) else []:
            commit = item.get("commit", {})
            result.append(
                {
                    "sha": item["sha"],
                    "short": item["sha"][:7],
                    "message": str(commit.get("message", "")).split("\n", 1)[0][:140],
                    "author": (commit.get("author") or {}).get("name", ""),
                    "date": (commit.get("author") or {}).get("date"),
                }
            )
        return result

    def pulls(self, owner: str, name: str, limit: int = 15) -> list[dict[str, Any]]:
        items = self._get(
            f"/repos/{owner}/{name}/pulls",
            {"state": "open", "sort": "updated", "direction": "desc", "per_page": str(limit)},
        )
        return [
            {
                "number": item["number"],
                "title": str(item.get("title", ""))[:200],
                "author": (item.get("user") or {}).get("login", ""),
                "updated_at": item.get("updated_at"),
                "draft": bool(item.get("draft")),
                "html_url": item["html_url"],
                "head": item["head"]["ref"],
                "base": item["base"]["ref"],
            }
            for item in items
        ]

    def pull(self, owner: str, name: str, number: int) -> dict[str, Any]:
        return dict(self._get(f"/repos/{owner}/{name}/pulls/{number}"))

    def pull_files(self, owner: str, name: str, number: int) -> list[dict[str, Any]]:
        files = self._get(f"/repos/{owner}/{name}/pulls/{number}/files", {"per_page": "100"})
        return [f for f in files if isinstance(f, dict)]
