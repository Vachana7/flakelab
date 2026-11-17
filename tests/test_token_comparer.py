"""Unit tests for compare_tokens() in pipedelta/permissions.py."""

import yaml

from pipedelta.permissions import (
    CANNOT_TELL,
    INCREASE,
    NONE,
    OTHER_SCOPES,
    READ,
    REDUCTION,
    UNKNOWN,
    WRITE,
    Change,
    compare_tokens,
    job_tokens,
    parse_block,
    repository_default,
)


def tok(block):
    return parse_block(block, "job")


# --- increases and reductions -------------------------------------------------


def test_identical_tokens_have_no_changes():
    assert compare_tokens(tok({"contents": "read"}), tok({"contents": "read"})) == []


def test_read_to_write_is_an_increase():
    assert compare_tokens(tok({"contents": "read"}), tok({"contents": "write"})) == [
        Change("contents", READ, WRITE, INCREASE)
    ]


def test_write_to_read_is_a_reduction():
    assert compare_tokens(tok({"contents": "write"}), tok({"contents": "read"})) == [
        Change("contents", WRITE, READ, REDUCTION)
    ]


def test_none_to_read_is_an_increase_and_write_to_none_is_a_reduction():
    assert compare_tokens(tok({}), tok({"issues": "read"})) == [
        Change("issues", NONE, READ, INCREASE)
    ]
    assert compare_tokens(tok({"issues": "write"}), tok({})) == [
        Change("issues", WRITE, NONE, REDUCTION)
    ]


# --- scopes present on only one side -----------------------------------------


def test_scope_listed_only_after_is_compared_with_the_old_default():
    # Before: only contents is listed, so issues was none.
    changes = compare_tokens(
        tok({"contents": "read"}), tok({"contents": "read", "issues": "write"})
    )
    assert changes == [Change("issues", NONE, WRITE, INCREASE)]


def test_scope_listed_only_before_is_compared_with_the_new_default():
    changes = compare_tokens(
        tok({"contents": "write", "issues": "write"}), tok({"issues": "write"})
    )
    assert changes == [Change("contents", WRITE, NONE, REDUCTION)]


def test_one_change_can_contain_an_increase_and_a_reduction():
    changes = compare_tokens(tok({"contents": "write"}), tok({"issues": "write"}))
    assert Change("contents", WRITE, NONE, REDUCTION) in changes
    assert Change("issues", NONE, WRITE, INCREASE) in changes
    assert len(changes) == 2


# --- the "all" forms ---------------------------------------------------------


def test_read_all_to_write_all_changes_every_other_scope():
    changes = compare_tokens(tok("read-all"), tok("write-all"))
    assert Change(OTHER_SCOPES, READ, WRITE, INCREASE) in changes


def test_listed_block_to_write_all_reports_listed_scope_and_the_rest():
    changes = compare_tokens(tok({"contents": "read"}), tok("write-all"))
    assert Change("contents", READ, WRITE, INCREASE) in changes
    assert Change(OTHER_SCOPES, NONE, WRITE, INCREASE) in changes


def test_write_all_to_a_listed_block_is_all_reductions():
    changes = compare_tokens(tok("write-all"), tok({"contents": "read"}))
    assert changes
    assert all(c.kind == REDUCTION for c in changes)


def test_scope_already_at_the_new_level_is_not_reported_again():
    # contents was write and stays write; only the rest changes.
    changes = compare_tokens(tok({"contents": "write"}), tok("write-all"))
    assert not any(c.scope == "contents" for c in changes)
    assert Change(OTHER_SCOPES, NONE, WRITE, INCREASE) in changes


def test_special_scope_is_listed_separately_only_when_it_differs_from_the_rest():
    changes = compare_tokens(tok({}), tok("write-all"))
    # vulnerability-alerts only reaches read under write-all, so it gets its own line
    assert Change("vulnerability-alerts", NONE, READ, INCREASE) in changes
    # id-token follows the rest (none -> write), so it is not repeated
    assert not any(c.scope == "id-token" for c in changes)


# --- unknown is never called an increase or a reduction ----------------------


def test_from_repository_default_to_an_explicit_block_cannot_be_ranked():
    changes = compare_tokens(repository_default(), tok({"contents": "write"}))
    assert changes
    assert all(c.kind == CANNOT_TELL for c in changes)
    assert Change("contents", UNKNOWN, WRITE, CANNOT_TELL) in changes


def test_from_an_explicit_block_to_repository_default_cannot_be_ranked():
    changes = compare_tokens(tok({"contents": "read"}), repository_default())
    assert changes
    assert all(c.kind == CANNOT_TELL for c in changes)


def test_repository_default_on_both_sides_is_no_change():
    assert compare_tokens(repository_default(), repository_default()) == []


def test_invalid_level_shows_up_as_cannot_tell_for_that_scope_only():
    changes = compare_tokens(
        tok({"contents": "read"}), tok({"contents": "read", "id-token": "read"})
    )
    assert changes == [Change("id-token", NONE, UNKNOWN, CANNOT_TELL)]


# --- location of the block does not matter -----------------------------------


def _tokens(text):
    return job_tokens(yaml.safe_load(text))


def test_moving_an_identical_block_from_workflow_to_job_is_no_change():
    at_workflow = "on: push\npermissions:\n  contents: read\njobs:\n  build:\n    runs-on: x\n"
    at_job = "on: push\njobs:\n  build:\n    runs-on: x\n    permissions:\n      contents: read\n"
    before, after = _tokens(at_workflow)["build"], _tokens(at_job)["build"]
    assert before.source == "workflow"
    assert after.source == "job"
    assert compare_tokens(before, after) == []


def test_order_and_explicit_none_do_not_create_changes():
    a = tok({"contents": "read", "issues": "write", "packages": "none"})
    b = tok({"issues": "write", "contents": "read"})
    assert compare_tokens(a, b) == []


# --- job_tokens --------------------------------------------------------------


def test_job_tokens_resolves_each_job_and_survives_odd_input():
    text = (
        "on: push\npermissions: read-all\njobs:\n"
        "  a:\n    runs-on: x\n"
        "  b:\n    runs-on: x\n    permissions: {}\n"
    )
    tokens = _tokens(text)
    assert tokens["a"].level("contents") == READ
    assert tokens["b"].level("contents") == NONE
    assert job_tokens(None) == {}
    assert job_tokens("text") == {}
    assert job_tokens({"jobs": ["x"]}) == {}
    assert job_tokens({"jobs": {"a": None}}) == {}
