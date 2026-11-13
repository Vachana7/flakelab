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
