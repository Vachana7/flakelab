"""Unit tests for the token model and the resolver in pipedelta/permissions.py."""

import pytest
import yaml

from pipedelta.permissions import (
    NONE,
    READ,
    UNKNOWN,
    WRITE,
    Token,
    effective_token,
    parse_block,
    repository_default,
)


def resolve(text: str, job: str = "build") -> Token:
    """Load a workflow from YAML text and resolve one job's token."""
    workflow = yaml.safe_load(text)
    return effective_token(workflow, workflow["jobs"][job])


# --- the token model: one test per row of the table ---------------------------


def test_write_all_gives_write_on_every_scope():
    token = parse_block("write-all", "workflow")
    assert token.level("contents") == WRITE
    assert token.level("issues") == WRITE


def test_read_all_gives_read_on_every_scope():
    token = parse_block("read-all", "workflow")
    assert token.level("contents") == READ
    assert token.level("packages") == READ


def test_listed_scope_keeps_its_level_and_unlisted_scopes_become_none():
    token = parse_block({"contents": "write"}, "job")
    assert token.level("contents") == WRITE
    assert token.level("issues") == NONE


def test_empty_block_gives_nothing():
    token = parse_block({}, "job")
    assert token.known
    assert token.level("contents") == NONE


def test_explicit_none_is_the_same_as_not_listing_the_scope():
    token = parse_block({"contents": "read", "issues": "none"}, "job")
    assert token.level("issues") == NONE


# --- the resolver: which block wins ------------------------------------------

WRITE_ALL_WORKFLOW = "on: push\npermissions: write-all\njobs:\n  build:\n    runs-on: x\n"


def test_job_inherits_the_workflow_block_when_it_has_none():
    token = resolve(WRITE_ALL_WORKFLOW)
    assert token.level("contents") == WRITE
    assert token.source == "workflow"


def test_job_block_replaces_the_workflow_block_completely():
    token = resolve(WRITE_ALL_WORKFLOW + "    permissions:\n      contents: read\n")
    assert token.level("contents") == READ
    assert token.level("issues") == NONE  # not inherited from write-all
    assert token.source == "job"


def test_empty_job_block_under_write_all_gives_nothing():
    token = resolve(WRITE_ALL_WORKFLOW + "    permissions: {}\n")
    assert token.level("contents") == NONE


def test_each_job_is_resolved_on_its_own():
    text = (
        "on: push\npermissions:\n  contents: read\njobs:\n"
        "  build:\n    runs-on: x\n"
        "  release:\n    runs-on: x\n    permissions:\n      contents: write\n"
    )
    assert resolve(text, "build").level("contents") == READ
    assert resolve(text, "release").level("contents") == WRITE


# --- unknown is never guessed ------------------------------------------------


def test_no_block_anywhere_is_the_repository_default_and_is_unknown():
    token = resolve("on: push\njobs:\n  build:\n    runs-on: x\n")
    assert not token.known
    assert token.level("contents") == UNKNOWN
    assert token.source == "repository default"
    assert token == repository_default()


@pytest.mark.parametrize("value", [None, ["contents"], 5, "everything", True])
def test_undocumented_forms_are_unknown_not_guessed(value):
    assert not parse_block(value, "job").known


def test_unrecognised_level_for_one_scope_is_unknown_for_that_scope_only():
    token = parse_block({"contents": "${{ inputs.level }}", "issues": "read"}, "job")
    assert token.level("contents") == UNKNOWN
    assert token.level("issues") == READ


def test_a_level_that_is_not_text_does_not_crash_and_is_unknown():
    token = parse_block({"contents": ["read"], "issues": {"a": 1}}, "job")
    assert token.level("contents") == UNKNOWN
    assert token.level("issues") == UNKNOWN


def test_read_all_on_a_scope_without_a_read_level_is_unknown():
    # GitHub's documentation does not say what read-all does for id-token.
    assert parse_block("read-all", "workflow").level("id-token") == UNKNOWN
    assert parse_block("write-all", "workflow").level("id-token") == WRITE


def test_write_all_gives_only_read_on_a_scope_without_a_write_level():
    assert parse_block("write-all", "workflow").level("vulnerability-alerts") == READ


# --- id-token, invalid combinations and unrecognised names --------------------


def test_id_token_listed_as_write_is_write():
    assert parse_block({"id-token": "write"}, "job").level("id-token") == WRITE


def test_id_token_not_listed_is_none():
    assert parse_block({"contents": "read"}, "job").level("id-token") == NONE


def test_id_token_read_is_not_a_documented_level_so_it_is_unknown():
    token = parse_block({"id-token": "read", "contents": "read"}, "job")
    assert token.level("id-token") == UNKNOWN
    assert token.level("contents") == READ  # the rest of the block is still understood


def test_write_on_a_scope_without_a_write_level_is_unknown():
    assert (
        parse_block({"vulnerability-alerts": "write"}, "job").level("vulnerability-alerts")
        == UNKNOWN
    )
    assert (
        parse_block({"vulnerability-alerts": "read"}, "job").level("vulnerability-alerts") == READ
    )


@pytest.mark.parametrize(
    ("block", "scope"),
    [
        ({"id-token": "read"}, "id-token"),
        ({"copilot-requests": "read"}, "copilot-requests"),
        ({"vulnerability-alerts": "write"}, "vulnerability-alerts"),
        ({"contents": "admin"}, "contents"),
        ({"contents": ""}, "contents"),
    ],
)
def test_an_invalid_combination_is_never_reported_as_a_real_level(block, scope):
    assert parse_block(block, "job").level(scope) not in (NONE, READ, WRITE)


def test_unrecognised_scope_name_is_kept_as_written():
    token = parse_block({"made-up-scope": "write"}, "job")
    assert token.level("made-up-scope") == WRITE
    assert ("made-up-scope", WRITE) in token.scopes


def test_all_forms_cover_names_we_have_never_heard_of():
    assert parse_block("write-all", "job").level("scope-added-next-year") == WRITE
    assert parse_block({}, "job").level("scope-added-next-year") == NONE


def test_scope_names_are_case_sensitive_for_now():
    # Documented limit, pinned on purpose: we have not verified how GitHub
    # treats capital letters, so the name is kept exactly as written.
    token = parse_block({"Contents": "write"}, "job")
    assert token.level("Contents") == WRITE
    assert token.level("contents") == NONE


# --- equality: needed later to say "nothing changed" -------------------------


def test_same_permissions_are_equal_whichever_block_they_came_from():
    assert parse_block({"contents": "read"}, "job") == parse_block({"contents": "read"}, "workflow")


def test_writing_none_explicitly_makes_no_difference_to_equality():
    assert parse_block({"contents": "read", "issues": "none"}, "job") == parse_block(
        {"contents": "read"}, "job"
    )


def test_order_of_scopes_in_the_file_does_not_matter():
    a = parse_block({"contents": "read", "issues": "write"}, "job")
    b = parse_block({"issues": "write", "contents": "read"}, "job")
    assert a == b


def test_different_permissions_are_not_equal():
    assert parse_block("read-all", "job") != parse_block("write-all", "job")
    assert parse_block({}, "job") != repository_default()
