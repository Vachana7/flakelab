"""Powers a change takes away. Written before the implementation."""

import subprocess

import pytest

from pipedelta.cli import compare_commits, main
from pipedelta.delta import compare, overall

FULL = """on: [push, pull_request_target]
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: someone/tool@v1
      - run: curl https://example.org/x
        env:
          K: ${{ secrets.KEY }}
  deploy:
    runs-on: self-hosted
    steps:
      - run: echo "${{ github.event.pull_request.title }}"
      - run: echo abc | base64 -d | bash
"""


def reduced(findings):
    return {(f.power.kind, f.power.name) for f in findings if f.change == "reduced"}


REMOVALS = [
    ("trigger", "pull_request_target", ("on: [push, pull_request_target]", "on: [push]")),
    ("secret", "KEY", ("        env:\n          K: ${{ secrets.KEY }}\n", "")),
    ("action", "someone/tool@v1", ("      - uses: someone/tool@v1\n", "")),
    ("network", "example.org", ("curl https://example.org/x", "make")),
    ("runner", "self-hosted", ("runs-on: self-hosted", "runs-on: ubuntu-latest")),
    ("injection", None, ('      - run: echo "${{ github.event.pull_request.title }}"\n', "")),
    ("hidden", None, ("      - run: echo abc | base64 -d | bash\n", "")),
]


@pytest.mark.parametrize(("kind", "name", "edit"), REMOVALS, ids=[r[0] for r in REMOVALS])
def test_removing_each_kind_of_power_is_reported_as_a_reduction(kind, name, edit):
    new = FULL.replace(*edit)
    assert new != FULL
    findings = compare(FULL, new)
    kinds = {k for k, _ in reduced(findings)}
    assert kind in kinds
    if name:
        assert (kind, name) in reduced(findings)
    assert overall(findings) == "none"  # a removal never raises the level


def test_deleting_a_job_reports_the_powers_only_that_job_had():
    new = FULL[: FULL.index("  deploy:")]
    findings = compare(FULL, new)
    kinds = {k for k, _ in reduced(findings)}
    assert {"runner", "injection", "hidden"} <= kinds
    assert overall(findings) == "none"


def test_deleting_a_job_does_not_report_powers_another_job_still_has():
    # 'build' still has contents: write, the secret, the action and the network call.
    new = FULL[: FULL.index("  deploy:")]
    kinds = {k for k, _ in reduced(compare(FULL, new))}
    assert "secret" not in kinds
    assert "action" not in kinds
    assert "permission" not in kinds


def test_deleting_the_only_job_with_write_access_reports_the_permission_reduction():
    two = (
        "on: push\njobs:\n"
        "  build:\n    runs-on: x\n    permissions:\n      contents: read\n    steps:\n      - run: make\n"
        "  release:\n    runs-on: x\n    permissions:\n      contents: write\n    steps:\n      - run: make\n"
    )
    new = two[: two.index("  release:")]
    assert ("permission", "contents: none") in reduced(compare(two, new))


def test_deleting_the_whole_file_reports_everything_as_reduced():
    findings = compare(FULL, None)
    assert findings
    assert all(f.change == "reduced" for f in findings)
    kinds = {k for k, _ in reduced(findings)}
    assert {"trigger", "secret", "action", "network", "runner", "permission"} <= kinds
    assert overall(findings) == "none"


def test_renaming_a_job_reports_no_removals():
    new = FULL.replace("  build:", "  compile:")
    assert reduced(compare(FULL, new)) == set()


def test_moving_a_step_to_another_job_reports_no_removals():
    step = "      - uses: someone/tool@v1\n"
    new = FULL.replace(step, "") + step
    assert reduced(compare(FULL, new)) == set()


def test_nothing_removed_means_no_reductions():
    assert reduced(compare(FULL, FULL)) == set()


def test_removals_pass_the_strictest_gate(tmp_path):
    old = tmp_path / "old.yml"
    new = tmp_path / "new.yml"
    old.write_text(FULL)
    new.write_text(FULL[: FULL.index("  deploy:")])
    assert main(["diff", str(old), str(new), "--fail-on", "low"]) == 0


def test_a_deleted_workflow_file_is_reported_in_git_mode(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (wf / "ci.yml").write_text(FULL)
    git("add", "-A")
    git("commit", "-qm", "base")
    git("rm", "-q", ".github/workflows/ci.yml")
    git("commit", "-qm", "delete workflow")
    monkeypatch.chdir(tmp_path)
    results = compare_commits("HEAD~1", "HEAD")
    findings = results[".github/workflows/ci.yml"]
    assert findings
    assert all(f.change == "reduced" for f in findings)
