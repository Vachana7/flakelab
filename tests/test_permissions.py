"""Effective permissions: what each job's token really gets.

These regression tests were written BEFORE the fix and failed on version 0.3.0.
"""

from pipedelta.delta import compare, overall

JOB = "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
STEP = "    steps:\n      - run: make\n"


def changes(findings):
    """(change, level, scope text) for every permission finding."""
    return [
        (getattr(f, "change", "gained"), f.level, f.power.name)
        for f in findings
        if f.power.kind == "permission"
    ]


def test_case1_removing_a_job_limit_under_write_all_is_an_escalation():
    # The job had its own read-only block. Deleting it makes the job inherit write-all.
    old = (
        "on: push\npermissions: write-all\n"
        + JOB
        + "    permissions:\n      contents: read\n"
        + STEP
    )
    new = "on: push\npermissions: write-all\n" + JOB + STEP
    findings = compare(old, new)
    assert overall(findings) == "high"
    assert any(change == "gained" and level == "high" for change, level, _ in changes(findings))


def test_case2_widening_the_workflow_block_does_not_touch_a_job_with_its_own_block():
    # The only job keeps its own read-only block, so its token does not change.
    old = (
        "on: push\npermissions:\n  contents: read\n"
        + JOB
        + "    permissions:\n      contents: read\n"
        + STEP
    )
    new = (
        "on: push\npermissions:\n  contents: write\n"
        + JOB
        + "    permissions:\n      contents: read\n"
        + STEP
    )
    assert changes(compare(old, new)) == []


def test_case3_a_new_job_block_also_removes_what_it_does_not_list():
    # The job used to inherit contents: write. Its new block names only issues,
    # so contents drops to none. Both the gain and the loss must be reported.
    old = "on: push\npermissions:\n  contents: write\n" + JOB + STEP
    new = (
        "on: push\npermissions:\n  contents: write\n"
        + JOB
        + "    permissions:\n      issues: write\n"
        + STEP
    )
    found = changes(compare(old, new))
    assert any(change == "gained" and "issues" in name for change, _, name in found)
    assert any(change == "reduced" and "contents" in name for change, _, name in found)


# --- Stage 1: invalid permission lines must not look like real gains ----------

BASE = "on: push\npermissions:\n  contents: read\n" + JOB + STEP


def _with_line(line: str) -> str:
    return BASE.replace("  contents: read\n", "  contents: read\n" + line)


def _assert_reported_as_unknown(findings, scope):
    about_scope = [f for f in findings if f.power.kind == "permission" and scope in f.power.name]
    assert about_scope, "the invalid line must be mentioned, not silently dropped"
    for f in about_scope:
        assert getattr(f, "change", "gained") == "unknown"
        assert f.level != "high"
    assert overall(findings) != "high"


def test_invalid_id_token_read_is_reported_as_unknown_not_as_a_gain():
    findings = compare(BASE, _with_line("  id-token: read\n"))
    _assert_reported_as_unknown(findings, "id-token")


def test_invalid_vulnerability_alerts_write_is_not_a_high_escalation():
    findings = compare(BASE, _with_line("  vulnerability-alerts: write\n"))
    _assert_reported_as_unknown(findings, "vulnerability-alerts")


def test_invalid_level_word_is_reported_as_unknown_not_as_read():
    new = BASE.replace("  contents: read\n", "  contents: admin\n")
    findings = compare(BASE, new)
    _assert_reported_as_unknown(findings, "contents")
