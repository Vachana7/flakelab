"""Post the report as one pull request comment, updating it on later runs."""

from __future__ import annotations

import json
import os
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


# The account that writes comments when a workflow uses its built-in token.
DEFAULT_AUTHOR = "github-actions[bot]"


def _is_ours(comment: Any, author: str) -> bool:
    """Is this an earlier PipeDelta report written by our own account?

    The hidden marker alone is not enough: anyone can paste it into a
    comment. If we tried to update a stranger's comment, GitHub would refuse
    and no report would be posted at all.
    """
    if not isinstance(comment, dict):
        return False
    user = comment.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    return login == author and MARKER in (comment.get("body") or "")


def upsert_comment(repo: str, pr_number: int, token: str, body: str) -> str:
    """Create the PipeDelta comment, or edit our own earlier one.

    Returns "created", "updated", or "skipped: <reason>". Never raises:
    a missing comment must not hide the real result of the check.

    A token that belongs to another account (not the built-in one) can name
    that account in the PIPEDELTA_COMMENT_AUTHOR environment variable.
    """
    author = os.environ.get("PIPEDELTA_COMMENT_AUTHOR") or DEFAULT_AUTHOR
    try:
        comments = _call(
            "GET", f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100", token
        )
        for comment in comments if isinstance(comments, list) else []:
            if not _is_ours(comment, author):
                continue
            try:
                _call(
                    "PATCH",
                    f"{API}/repos/{repo}/issues/comments/{comment['id']}",
                    token,
                    {"body": body},
                )
                return "updated"
            except urllib.error.HTTPError:
                break  # could not edit it: post a fresh report instead
        _call("POST", f"{API}/repos/{repo}/issues/{pr_number}/comments", token, {"body": body})
        return "created"
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        return f"skipped: {error}"
