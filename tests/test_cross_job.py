"""A power that leaves one job and appears in another.

KNOWN LIMITATION, kept as evidence. PipeDelta rates a power by whether the
workflow has it anywhere, not by which job holds it. The five tests marked
``known_gap`` describe the correct behaviour and FAIL today. They are marked
as expected failures so the suite stays green while the gap stays visible.
``strict=True`` means that the day the behaviour is fixed, these tests will
report an unexpected pass and the marker must be removed.

Design notes and the scenarios to implement: docs/CROSS_JOB.md
"""

import pytest

from pipedelta.delta import compare, overall

known_gap = pytest.mark.xfail(
    strict=True,
    reason="cross-job movement is not modelled yet; see docs/CROSS_JOB.md",
)

HEAD = "on: push\npermissions:\n  contents: read\njobs:\n"
SECRET = "        env:\n          K: ${{ secrets.DEPLOY_KEY }}\n"


def job(name, *, body="      - run: make\n", runner="ubuntu-latest", perms=""):
    return f"  {name}:\n    runs-on: {runner}\n{perms}    steps:\n{body}"


def about(findings, kind):
    return [f for f in findings if f.power.kind == kind]


# --- moves that change how exposed the power is: must NOT be merely low --------


@known_gap
def test_secret_moves_into_a_job_that_already_contacts_an_outside_address():
    quiet = job("build", body="      - run: make\n" + SECRET)
    talks = job("report", body="      - run: curl https://stats.example.org/up\n")
    old = HEAD + quiet + talks
    new = (
        HEAD
        + job("build")
        + job("report", body="      - run: curl https://stats.example.org/up\n" + SECRET)
    )
    findings = compare(old, new)
    assert overall(findings) == "high"
    assert any("report" in f.message for f in about(findings, "secret"))


@known_gap
def test_secret_moves_into_a_job_that_pastes_outsider_text_into_a_command():
    inject = '      - run: echo "${{ github.event.pull_request.title }}"\n'
    old = HEAD + job("build", body="      - run: make\n" + SECRET) + job("label", body=inject)
    new = HEAD + job("build") + job("label", body=inject + SECRET)
    assert overall(compare(old, new)) == "high"


@known_gap
def test_secret_moves_onto_a_self_hosted_runner():
    old = (
        HEAD
        + job("build", body="      - run: make\n" + SECRET)
        + job("bench", runner="self-hosted")
    )
    new = (
        HEAD
        + job("build")
        + job("bench", runner="self-hosted", body="      - run: make\n" + SECRET)
    )
    findings = about(compare(old, new), "secret")
    assert findings
    assert max(findings, key=lambda f: ["low", "medium", "high"].index(f.level)).level != "low"


@known_gap
def test_outside_action_moves_into_a_job_whose_token_can_write():
    step = "      - uses: someone/tool@v1\n"
    write = "    permissions:\n      contents: write\n"
    old = HEAD + job("lint", body=step) + job("release", perms=write)
    new = HEAD + job("lint") + job("release", perms=write, body=step)
    findings = about(compare(old, new), "action")
    assert any(f.level == "high" and "release" in f.message for f in findings)


@known_gap
def test_leaving_a_job_is_reported_even_when_the_power_stays_elsewhere():
    old = (
        HEAD
        + job("build", body="      - run: make\n" + SECRET)
        + job("deploy", body="      - run: make\n" + SECRET)
    )
    new = HEAD + job("build") + job("deploy", body="      - run: make\n" + SECRET)
    reduced = [f for f in about(compare(old, new), "secret") if f.change == "reduced"]
    assert reduced
    assert "build" in reduced[0].message


# --- controls: these must stay quiet ----------------------------------------


def test_control_renamed_job_is_not_an_escalation_and_not_a_removal():
    old = HEAD + job("build", body="      - run: curl https://stats.example.org/up\n" + SECRET)
    new = old.replace("  build:", "  compile:")
    findings = compare(old, new)
    assert overall(findings) in ("none", "low")
    assert not [f for f in findings if f.change == "reduced"]


def test_control_move_between_two_equally_exposed_jobs_stays_low():
    old = HEAD + job("a", body="      - run: make\n" + SECRET) + job("b")
    new = HEAD + job("a") + job("b", body="      - run: make\n" + SECRET)
    assert overall(compare(old, new)) in ("none", "low")


def test_control_secret_added_to_a_second_job_with_the_same_exposure_stays_low():
    old = HEAD + job("a", body="      - run: make\n" + SECRET) + job("b")
    new = (
        HEAD
        + job("a", body="      - run: make\n" + SECRET)
        + job("b", body="      - run: make\n" + SECRET)
    )
    assert overall(compare(old, new)) in ("none", "low")
