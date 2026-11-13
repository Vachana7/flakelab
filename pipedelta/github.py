"""Post the report as one pull request comment, updating it on later runs."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .report import MARKER

API = "https://api.github.com"


def _call(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read() or b"null")


def upsert_comment(repo: str, pr_number: int, token: str, body: str) -> str:
    """Create the PipeDelta comment, or edit it if it already exists.

    Returns "created", "updated", or "skipped: <reason>". Never raises:
    a missing comment must not hide the real result of the check.
    """
    try:
        comments = _call(
            "GET", f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100", token
        )
        for comment in comments:
            if MARKER in (comment.get("body") or ""):
                _call(
                    "PATCH",
                    f"{API}/repos/{repo}/issues/comments/{comment['id']}",
                    token,
                    {"body": body},
                )
                return "updated"
        _call("POST", f"{API}/repos/{repo}/issues/{pr_number}/comments", token, {"body": body})
        return "created"
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        return f"skipped: {error}"
