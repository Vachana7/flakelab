"""Tests for bugs found in the 13 Nov review. Each one failed before its fix."""

import json
import subprocess

from pipedelta.cli import compare_commits, main
from pipedelta.delta import compare, overall
from pipedelta.report import render_markdown, render_text

BASE = """name: CI
on: [push]
permissions:
  contents: read
jobs:
  t:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def kinds(findings):
    return {(f.level, f.power.kind, f.power.name) for f in findings}


def test_reusable_workflow_from_this_repository_is_not_outside_code():
    new = BASE + "  call:\n    uses: ./.github/workflows/other.yml\n"
    assert not any(f.power.kind == "action" for f in compare(BASE, new))


def test_reusable_workflow_from_another_repository_is_outside_code():
    new = BASE + "  call:\n    uses: someone/repo/.github/workflows/x.yml@main\n"
    assert overall(compare(BASE, new)) == "high"


def test_removing_the_permissions_block_is_reported():
    new = BASE.replace("permissions:\n  contents: read\n", "")
    findings = compare(BASE, new)
    assert any(f.level == "medium" and "no limit" in f.message for f in findings)


def test_job_level_permissions_count_as_a_limit():
    new = BASE.replace("permissions:\n  contents: read\n", "").replace(
        "    runs-on: ubuntu-latest",
        "    runs-on: ubuntu-latest\n    permissions:\n      contents: read",
    )
    assert not any("no limit" in f.message for f in compare(BASE, new))


def test_built_in_token_is_not_treated_as_a_stored_secret():
    new = BASE + "        env:\n          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"
    assert overall(compare(BASE, new)) == "low"


def test_self_hosted_runner_in_group_form_is_seen():
    new = BASE.replace(
        "runs-on: ubuntu-latest", "runs-on:\n      group: x\n      labels: [self-hosted, linux]"
    )
    assert any(f.power.kind == "runner" for f in compare(BASE, new))


def test_odd_shapes_do_not_crash():
    for text in [
        "on: push\njobs:\n  - a\n",
        "on: push\njobs:\n  t:\n    steps: nope\n",
        "on: push\njobs:\n  t:\n    steps:\n      - uses: 123\n      - run: 5\n",
        "",
        "on: push\npermissions: [a]\njobs: {}\n",
        "just a string",
        "on:\n  push:\njobs:\n  t: null\n",
    ]:
        compare(BASE, text)
        compare(text, BASE)


def test_job_name_cannot_inject_markup_into_the_comment():
    evil = BASE.replace("  t:\n", '  "[click](http://evil.example) @everyone `x` <b>":\n')
    evil += "        env:\n          K: ${{ secrets.KEY }}\n"
    text = render_markdown({"ci.yml": compare(BASE, evil)})
    assert "[click](http" not in text
    assert "@everyone" not in text
    assert "<b>" not in text
    assert "`x`" not in text


def test_control_characters_are_removed_from_terminal_output():
    evil = BASE.replace("  t:\n", '  "a\\e[31m\\nFAKE LINE":\n')
    evil += "        env:\n          K: ${{ secrets.KEY }}\n"
    text = render_text({"ci.yml": compare(BASE, evil)})
    assert "\x1b" not in text
    assert not any(line.startswith("FAKE LINE") for line in text.splitlines())


def _repo(tmp_path):
    def git(*args):
        out = subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        )
        return out.stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return git


RISKY = BASE + "      - uses: someone/tool@v1\n        env:\n          K: ${{ secrets.KEY }}\n"


def test_renaming_a_workflow_file_does_not_make_everything_look_new(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    wf = tmp_path / ".github" / "workflows"
    (wf / "ci.yml").write_text(RISKY)
    git("add", "-A")
    git("commit", "-qm", "base")
    git("mv", ".github/workflows/ci.yml", ".github/workflows/build.yml")
    git("commit", "-qm", "rename")
    monkeypatch.chdir(tmp_path)
    results = compare_commits("HEAD~1", "HEAD")
    assert all(findings == [] for findings in results.values())


def test_action_compares_with_the_branch_point_not_the_branch_tip(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    wf = tmp_path / ".github" / "workflows"
    (wf / "ci.yml").write_text(RISKY)
    git("add", "-A")
    git("commit", "-qm", "base with risky step")
    git("checkout", "-qb", "feature")
    (tmp_path / "README.md").write_text("docs only\n")
    git("add", "-A")
    git("commit", "-qm", "docs change")
    head = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    (wf / "ci.yml").write_text(BASE)  # main removes the risky step afterwards
    git("commit", "-qam", "main cleans up")
    base_tip = git("rev-parse", "HEAD")

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {"pull_request": {"number": 1, "base": {"sha": base_tip}, "head": {"sha": head}}}
        )
    )
    output = tmp_path / "out.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("PIPEDELTA_TOKEN", raising=False)
    # The pull request only changed README.md, so it must not be blamed.
    assert main(["action", "--fail-on", "low"]) == 0
    assert "level=none" in output.read_text()


def test_file_that_is_not_valid_yaml_gives_a_clear_error(tmp_path, capsys):
    bad = tmp_path / "bad.yml"
    bad.write_text("a: 1\n---\nb: 2\n")
    good = tmp_path / "good.yml"
    good.write_text(BASE)
    assert main(["diff", str(good), str(bad)]) == 2
    assert "could not read" in capsys.readouterr().err
