"""Effective permissions: what each job's token really gets.

These regression tests were written BEFORE the fix and failed on version 0.3.0.
"""

from pipedelta.cli import main
from pipedelta.delta import compare, overall
from pipedelta.report import render_markdown, render_text

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


# --- Stage 3: behaviour of the integrated comparison ---------------------------


def test_reductions_alone_pass_even_the_strictest_gate(tmp_path):
    old = tmp_path / "old.yml"
    new = tmp_path / "new.yml"
    old.write_text("on: push\npermissions:\n  contents: write\n" + JOB + STEP)
    new.write_text("on: push\npermissions:\n  contents: read\n" + JOB + STEP)
    assert main(["diff", str(old), str(new), "--fail-on", "low"]) == 0


def test_reduction_is_labelled_in_both_report_formats():
    old = "on: push\npermissions:\n  contents: write\n" + JOB + STEP
    new = "on: push\npermissions:\n  contents: read\n" + JOB + STEP
    results = {"ci.yml": compare(old, new)}
    assert "[REDUCED" in render_text(results)
    assert "| reduced |" in render_markdown(results)
    assert "no new powers" in render_markdown(results)


def test_moving_the_block_between_levels_reports_nothing():
    at_workflow = "on: push\npermissions:\n  contents: read\n" + JOB + STEP
    at_job = "on: push\n" + JOB + "    permissions:\n      contents: read\n" + STEP
    assert changes(compare(at_workflow, at_job)) == []
    assert changes(compare(at_job, at_workflow)) == []


def test_renaming_a_job_with_write_access_is_not_an_escalation():
    old = "on: push\npermissions:\n  contents: write\n" + JOB + STEP
    new = old.replace("  build:", "  compile:")
    findings = compare(old, new)
    assert overall(findings) != "high"
    assert all(f.level == "low" for f in findings if f.power.kind == "permission")


def test_a_genuinely_new_job_with_write_access_is_high():
    old = "on: push\npermissions:\n  contents: read\n" + JOB + STEP
    new = old + "  release:\n    runs-on: x\n    permissions:\n      contents: write\n" + STEP
    assert overall(compare(old, new)) == "high"


def test_one_workflow_level_change_is_one_finding_naming_every_job():
    two_jobs = JOB + STEP + "  test:\n    runs-on: x\n" + STEP
    old = "on: push\npermissions:\n  contents: read\n" + two_jobs
    new = "on: push\npermissions:\n  contents: write\n" + two_jobs
    found = [f for f in compare(old, new) if f.power.kind == "permission"]
    assert len(found) == 1
    assert "'build'" in found[0].message
    assert "'test'" in found[0].message


def test_removing_every_limit_is_unknown_and_medium_not_high():
    old = "on: push\npermissions:\n  contents: read\n" + JOB + STEP
    new = "on: push\n" + JOB + STEP
    found = [f for f in compare(old, new) if f.power.kind == "permission"]
    assert found
    assert all(f.change == "unknown" for f in found)
    assert overall(found) == "medium"


def test_first_explicit_limit_after_repository_default_is_not_called_an_increase():
    old = "on: push\n" + JOB + STEP
    new = "on: push\npermissions:\n  contents: write\n" + JOB + STEP
    found = [f for f in compare(old, new) if f.power.kind == "permission"]
    assert found
    assert all(f.change == "unknown" for f in found)
    assert overall(found) != "high"


def test_scope_name_cannot_inject_control_characters_or_markup():
    new = BASE.replace(
        "  contents: read\n", '  contents: read\n  "a\\e[31m\\nFAKE [x](http://e.example)": write\n'
    )
    results = {"ci.yml": compare(BASE, new)}
    text = render_text(results)
    assert "\x1b" not in text
    assert not any(line.startswith("FAKE") for line in text.splitlines())
    assert "[x](http" not in render_markdown(results)


def test_other_kinds_of_power_are_unaffected():
    new = BASE + "      - uses: someone/tool@v1\n        env:\n          K: ${{ secrets.KEY }}\n"
    kinds = {f.power.kind for f in compare(BASE, new)}
    assert kinds == {"action", "secret"}
