"""Version 0.5: rules from the 2025-2026 attacks, push review, SARIF, replay benchmark."""

import json
import subprocess
from pathlib import Path

import pytest

from pipedelta.cli import main
from pipedelta.delta import compare, overall
from pipedelta.report import render_sarif

BASE = """name: CI
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
"""
OUTSIDER = BASE.replace("on: push", "on: pull_request_target")


def high_kinds(findings):
    return {f.power.kind for f in findings if f.level == "high"}


def test_reading_runner_memory_is_high():
    after = BASE + "      - run: sudo cat /proc/$(pgrep -f Runner.Worker)/maps\n"
    assert "memory" in high_kinds(compare(BASE, after))


def test_workflow_that_writes_workflows_is_high():
    after = BASE + (
        "      - run: |\n"
        "          cp x.yml .github/workflows/new.yml\n"
        "          git add -A && git commit -m ci && git push\n"
    )
    assert "selfmod" in high_kinds(compare(BASE, after))


def test_mentioning_workflow_path_without_pushing_is_not_selfmod():
    after = BASE + "      - run: actionlint .github/workflows/ci.yml\n"
    assert "selfmod" not in {f.power.kind for f in compare(BASE, after)}


def test_adding_labels_is_medium_but_high_when_outsiders_can_start_it():
    step = "      - run: gh pr edit 1 --add-label safe-to-test\n"
    assert overall(compare(BASE, BASE + step)) == "medium"
    assert "selfmod" in high_kinds(compare(OUTSIDER, OUTSIDER + step))


def test_deleting_runs_or_force_pushing_is_high():
    for cmd in ("gh run delete $GITHUB_RUN_ID", "git push --force origin main"):
        assert "cover" in high_kinds(compare(BASE, BASE + f"      - run: {cmd}\n")), cmd


def test_oidc_permission_explains_identity_tokens():
    after = BASE.replace("contents: read", "contents: read\n  id-token: write")
    findings = compare(BASE, after)
    assert any("identity tokens" in f.message and f.level == "high" for f in findings)


def test_cache_is_low_normally_and_high_under_outsider_trigger():
    step = (
        "      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n"
        "        with:\n          cache: pip\n"
    )
    assert "cache" not in high_kinds(compare(BASE, BASE + step))
    assert "cache" in high_kinds(compare(OUTSIDER, OUTSIDER + step))


def test_all_secrets_at_once_is_high_even_without_network():
    after = BASE + "      - run: echo '${{ toJSON(secrets) }}' | base64\n"
    assert "secret" in high_kinds(compare(BASE, after))


def test_sarif_is_valid_shape():
    after = BASE + "      - run: gh run delete 1\n"
    sarif = json.loads(render_sarif({".github/workflows/ci.yml": compare(BASE, after)}))
    assert sarif["version"] == "2.1.0"
    result = sarif["runs"][0]["results"][0]
    assert result["level"] == "error"
    assert result["ruleId"].startswith("pipedelta/")
    loc = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert loc == ".github/workflows/ci.yml"


def test_every_replayed_incident_is_blocked():
    root = Path(__file__).parent.parent / "evaluation" / "replay"
    cases = sorted(p for p in root.iterdir() if p.is_dir())
    assert len(cases) >= 9
    for case in cases:
        before = case / "before.yml"
        level = overall(
            compare(
                before.read_text() if before.exists() else None, (case / "after.yml").read_text()
            )
        )
        assert level == "high", case.name


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


@pytest.fixture
def action_env(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    summary = tmp_path / "summary.md"
    sarif = tmp_path / "result.sarif"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PIPEDELTA_SARIF", str(sarif))
    monkeypatch.delenv("PIPEDELTA_TOKEN", raising=False)
    return out, summary, sarif


def _push_event(tmp_path, monkeypatch, before, after):
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {"ref": "refs/heads/main", "before": before, "after": after, "pusher": {"name": "x"}}
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))


def test_direct_push_of_secret_stealing_workflow_is_blocked(tmp_path, monkeypatch, action_env):
    out, summary, sarif = action_env
    git = _repo(tmp_path)
    (tmp_path / ".github/workflows/ci.yml").write_text(BASE)
    git("add", "-A")
    git("commit", "-qm", "base")
    before = git("rev-parse", "HEAD")
    ghost = Path(__file__).parent.parent / "evaluation/replay/r02-ghostaction-2026-direct-push"
    (tmp_path / ".github/workflows/security.yml").write_text((ghost / "after.yml").read_text())
    git("add", "-A")
    git("commit", "-qm", "Add Github Actions Security workflow")
    _push_event(tmp_path, monkeypatch, before, git("rev-parse", "HEAD"))
    assert main(["action"]) == 1
    assert "level=high" in out.read_text()
    assert "Push to `main`" in summary.read_text()
    assert json.loads(sarif.read_text())["runs"][0]["results"]


def test_push_with_unreadable_old_commit_fails_closed(tmp_path, monkeypatch, action_env):
    git = _repo(tmp_path)
    (tmp_path / ".github/workflows/ci.yml").write_text(BASE)
    git("add", "-A")
    git("commit", "-qm", "base")
    _push_event(tmp_path, monkeypatch, "1" * 40, git("rev-parse", "HEAD"))
    assert main(["action"]) == 2


def test_push_that_creates_a_branch_compares_with_parent(tmp_path, monkeypatch, action_env):
    out, _, _ = action_env
    git = _repo(tmp_path)
    (tmp_path / ".github/workflows/ci.yml").write_text(BASE)
    git("add", "-A")
    git("commit", "-qm", "base")
    (tmp_path / "README.md").write_text("docs\n")
    git("add", "-A")
    git("commit", "-qm", "docs")
    _push_event(tmp_path, monkeypatch, "0" * 40, git("rev-parse", "HEAD"))
    assert main(["action"]) == 0
    assert "level=none" in out.read_text()
