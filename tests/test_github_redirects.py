"""The GitHub token must never be sent anywhere but api.github.com."""

from __future__ import annotations

import urllib.request

import pytest

from pipedelta.web.github_client import GitHubError, build_opener


def _redirect(opener: urllib.request.OpenerDirector, target: str) -> object:
    handler = next(h for h in opener.handlers if hasattr(h, "redirect_request"))
    request = urllib.request.Request(
        "https://api.github.com/repos/o/r", headers={"Authorization": "Bearer secret"}
    )
    return handler.redirect_request(request, None, 302, "Found", {}, target)  # type: ignore[attr-defined]


def test_redirect_to_another_host_is_refused() -> None:
    with pytest.raises(GitHubError) as caught:
        _redirect(build_opener(), "https://evil.example/steal")
    assert caught.value.code == "bad_redirect"


def test_redirect_to_plain_http_is_refused() -> None:
    with pytest.raises(GitHubError):
        _redirect(build_opener(), "http://api.github.com/x")


def test_redirect_on_the_same_host_is_followed() -> None:
    new = _redirect(build_opener(), "https://api.github.com/repositories/1")
    assert new is not None


def test_look_alike_host_is_refused() -> None:
    with pytest.raises(GitHubError):
        _redirect(build_opener(), "https://api.github.com.evil.example/x")
