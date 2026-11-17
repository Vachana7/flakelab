"""Which pull request comment PipeDelta updates. Written before the fix.

No network is used: the function that talks to GitHub is replaced by a fake.
"""

import urllib.error

import pytest

from pipedelta import github
from pipedelta.report import MARKER

BOT = {"login": "github-actions[bot]", "type": "Bot"}
STRANGER = {"login": "mallory", "type": "User"}


class FakeGitHub:
    def __init__(self, comments, refuse_patch=False):
        self.comments = comments
        self.refuse_patch = refuse_patch
        self.calls = []

    def __call__(self, method, url, token, body=None):
        self.calls.append((method, url))
        if method == "GET":
            return self.comments
        if method == "PATCH" and self.refuse_patch:
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
        return {}

    def methods(self):
        return [method for method, _ in self.calls]

    def patched_ids(self):
        return [url.rsplit("/", 1)[1] for method, url in self.calls if method == "PATCH"]


@pytest.fixture
def fake(monkeypatch):
    def install(comments, **kwargs):
        api = FakeGitHub(comments, **kwargs)
        monkeypatch.setattr(github, "_call", api)
        monkeypatch.delenv("PIPEDELTA_COMMENT_AUTHOR", raising=False)
        return api

    return install


def test_first_run_creates_a_comment(fake):
    api = fake([])
    assert github.upsert_comment("o/r", 1, "t", "report") == "created"
    assert api.methods() == ["GET", "POST"]


def test_own_earlier_comment_is_updated(fake):
    api = fake([{"id": 11, "body": MARKER + "old", "user": BOT}])
    assert github.upsert_comment("o/r", 1, "t", "report") == "updated"
    assert api.patched_ids() == ["11"]


def test_marker_posted_by_someone_else_does_not_suppress_the_report(fake):
    # Before the fix: PipeDelta tried to edit mallory's comment, was refused,
    # swallowed the error and posted nothing.
    api = fake([{"id": 7, "body": MARKER + " nothing to see", "user": STRANGER}], refuse_patch=True)
    assert github.upsert_comment("o/r", 1, "t", "report") == "created"
    assert api.patched_ids() == []
    assert "POST" in api.methods()


def test_own_comment_is_chosen_even_when_a_stranger_posted_the_marker_first(fake):
    api = fake(
        [
            {"id": 7, "body": MARKER + " fake", "user": STRANGER},
            {"id": 11, "body": MARKER + " real", "user": BOT},
        ]
    )
    assert github.upsert_comment("o/r", 1, "t", "report") == "updated"
    assert api.patched_ids() == ["11"]


def test_if_the_update_is_refused_a_new_comment_is_posted_instead(fake):
    api = fake([{"id": 11, "body": MARKER, "user": BOT}], refuse_patch=True)
    assert github.upsert_comment("o/r", 1, "t", "report") == "created"
    assert api.methods() == ["GET", "PATCH", "POST"]


def test_comment_without_the_marker_is_left_alone(fake):
    api = fake([{"id": 3, "body": "LGTM", "user": BOT}])
    assert github.upsert_comment("o/r", 1, "t", "report") == "created"
    assert api.patched_ids() == []


def test_expected_author_can_be_set_for_other_tokens(fake, monkeypatch):
    api = fake([{"id": 5, "body": MARKER, "user": {"login": "ci-bot", "type": "User"}}])
    monkeypatch.setenv("PIPEDELTA_COMMENT_AUTHOR", "ci-bot")
    assert github.upsert_comment("o/r", 1, "t", "report") == "updated"
    assert api.patched_ids() == ["5"]


def test_malformed_comment_entries_do_not_crash(fake):
    fake([{"id": 1}, {"id": 2, "body": None, "user": None}, "junk"])
    assert github.upsert_comment("o/r", 1, "t", "report") == "created"


def test_no_network_is_reported_not_raised(monkeypatch):
    def down(*args, **kwargs):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(github, "_call", down)
    assert github.upsert_comment("o/r", 1, "t", "report").startswith("skipped")
