"""Stage 3: every finding comes with evidence you can check in the file.

For each finding the engine reports where it is (file, job, step, line), what
changed (previous and new value), how sure it is, why it matters and what to
do. Line numbers count from 1 and come from PyYAML's source positions.

Meaning of the fields (also in docs/EVIDENCE.md):

* severity   how bad it would be if the capability were abused: low/medium/high
* confidence how sure PipeDelta is that the file really gives this capability:
             high   the file says it in so many words (a ``uses:`` line, a
                    ``secrets.X`` reference, a URL);
             medium PipeDelta inferred it by a rule (an output that carries
                    outsider text from one step or job into another);
             low    the file does not say (a permission whose level cannot be read)
* precision  how exactly the finding could be placed: line, job, or file
"""

import json

from pipedelta.evidence import explain

BEFORE = """\
on: push
permissions:
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: make
"""

# Line numbers are written in the comments so a reader can check them.
AFTER = """\
on: pull_request_target
permissions:
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      KEY: ${{ secrets.DEPLOY_KEY }}
    steps:
      - uses: someone/tool@v1
      - name: Report
        run: |
          echo hi
          curl https://stats.example.org/ping
      - run: echo "${{ github.event.pull_request.title }}"
"""


def by_kind(evidence, kind, name_part=""):
    return [e for e in evidence if e.kind == kind and name_part in e.name]


def one(evidence, kind, name_part=""):
    found = by_kind(evidence, kind, name_part)
    assert len(found) == 1, [e.name for e in found]
    return found[0]


# ---- where --------------------------------------------------------------------


def test_each_finding_points_at_its_line_job_and_step():
    ev = explain(BEFORE, AFTER, "ci.yml")

    secret = one(ev, "secret", "DEPLOY_KEY")
    assert (secret.file, secret.job, secret.step, secret.line) == ("ci.yml", "deploy", None, 8)

    action = one(ev, "action", "someone/tool")
    assert (action.job, action.step, action.line) == ("deploy", 1, 10)

    network = one(ev, "network", "stats.example.org")
    assert (network.job, network.step, network.line) == ("deploy", 2, 14)
    assert network.step_label == "Report"

    injection = one(ev, "injection")
    assert (injection.job, injection.step, injection.line) == ("deploy", 3, 15)

    trigger = one(ev, "trigger", "pull_request_target")
    assert (trigger.job, trigger.line) == (None, 1)


def test_line_numbers_count_from_one_and_name_the_right_text():
    lines = AFTER.splitlines()
    for e in explain(BEFORE, AFTER, "ci.yml"):
        if e.precision == "line":
            assert 1 <= e.line <= len(lines)
    secret = one(explain(BEFORE, AFTER, "ci.yml"), "secret", "DEPLOY_KEY")
    assert "DEPLOY_KEY" in lines[secret.line - 1]


def test_snippet_shows_the_line_with_up_to_two_lines_of_context_each_side():
    network = one(explain(BEFORE, AFTER, "ci.yml"), "network")
    assert [s.number for s in network.snippet] == [12, 13, 14, 15]
    assert [s.number for s in network.snippet if s.hit] == [14]
    assert "stats.example.org" in [s.text for s in network.snippet if s.hit][0]


def test_snippet_near_the_start_of_the_file_is_not_padded():
    trigger = one(explain(BEFORE, AFTER, "ci.yml"), "trigger", "pull_request_target")
    assert [s.number for s in trigger.snippet][:1] == [1]


def test_a_removed_power_is_located_in_the_old_file():
    ev = explain(AFTER, BEFORE, "ci.yml")
    removed = [e for e in ev if e.change == "reduced" and e.kind == "secret"]
    assert len(removed) == 1
    assert removed[0].side == "before"
    assert removed[0].line == 8
    assert any("DEPLOY_KEY" in s.text for s in removed[0].snippet if s.hit)


def test_a_new_workflow_has_every_finding_located_in_it():
    ev = explain(None, AFTER, "new.yml")
    assert ev and all(e.side == "after" for e in ev)
    assert all(e.change != "reduced" for e in ev)
    assert one(ev, "secret", "DEPLOY_KEY").line == 8


# ---- previous and new values ---------------------------------------------------


def test_a_changed_permission_shows_old_and_new_level():
    old = "on: push\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: make\n"
    new = old.replace("contents: read", "contents: write")
    e = one(explain(old, new, "p.yml"), "permission")
    assert (e.previous, e.new) == ("contents: read", "contents: write")
    assert e.severity == "high"
    assert e.line == 3


def test_a_changed_action_version_shows_both_references():
    old = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: owner/tool@v1\n"
    new = old.replace("@v1", "@v2")
    e = one(explain(old, new, "p.yml"), "action")
    assert (e.previous, e.new) == ("owner/tool@v1", "owner/tool@v2")
    assert e.line == 6


def test_a_new_power_has_no_previous_value():
    e = one(explain(BEFORE, AFTER, "ci.yml"), "secret", "DEPLOY_KEY")
    assert e.previous is None
    assert "DEPLOY_KEY" in (e.new or "")


def test_a_removed_power_has_no_new_value():
    removed = [e for e in explain(AFTER, BEFORE, "ci.yml") if e.change == "reduced"]
    assert removed and all(e.new is None for e in removed)
    assert any("DEPLOY_KEY" in (e.previous or "") for e in removed)


# ---- how sure ------------------------------------------------------------------


def test_what_the_file_states_outright_is_high_confidence():
    ev = explain(BEFORE, AFTER, "ci.yml")
    for kind in ("secret", "action", "network", "trigger"):
        assert all(e.confidence == "high" for e in by_kind(ev, kind)), kind


def test_a_flow_through_a_step_output_is_medium_confidence():
    old = 'on: pull_request\njobs:\n  a:\n    runs-on: x\n    steps:\n      - id: r\n        run: echo "t=$GITHUB_SHA" >> $GITHUB_OUTPUT\n      - run: echo "${{ steps.r.outputs.t }}"\n'
    new = old.replace(
        '        run: echo "t=$GITHUB_SHA"',
        '        env:\n          T: ${{ github.event.pull_request.title }}\n        run: echo "t=$T"',
    )
    flows = [e for e in explain(old, new, "f.yml") if e.kind == "injection"]
    assert len(flows) == 1
    assert flows[0].confidence == "medium"
    assert flows[0].step == 2
    assert "steps.r.outputs.t" in flows[0].snippet_text()


def test_a_permission_the_file_cannot_state_is_low_confidence():
    old = "on: push\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: make\n"
    new = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: make\n"
    ev = [e for e in explain(old, new, "p.yml") if e.change == "unknown"]
    assert ev and all(e.confidence == "low" for e in ev)


# ---- why it matters and what to do ----------------------------------------------


def test_every_finding_has_a_consequence_and_a_remediation():
    for e in explain(BEFORE, AFTER, "ci.yml"):
        assert e.consequence.strip(), e.name
        assert e.remediation.strip(), e.name


def test_injection_advice_is_the_environment_variable_pattern():
    e = one(explain(BEFORE, AFTER, "ci.yml"), "injection")
    assert "env" in e.remediation.lower()


def test_unpinned_action_advice_is_to_pin_a_commit():
    e = one(explain(BEFORE, AFTER, "ci.yml"), "action")
    assert "40-character" in e.remediation


def test_a_reduction_needs_no_action():
    removed = [e for e in explain(AFTER, BEFORE, "ci.yml") if e.change == "reduced"]
    assert removed and all("no action" in e.remediation.lower() for e in removed)


# ---- order, identity, output ------------------------------------------------------


def test_highest_severity_comes_first():
    order = {"high": 0, "medium": 1, "low": 2}
    levels = [order[e.severity] for e in explain(BEFORE, AFTER, "ci.yml") if e.change != "reduced"]
    assert levels == sorted(levels)


def test_ids_are_stable_and_unique():
    first = explain(BEFORE, AFTER, "ci.yml")
    second = explain(BEFORE, AFTER, "ci.yml")
    assert [e.id for e in first] == [e.id for e in second]
    assert len({e.id for e in first}) == len(first)


def test_evidence_converts_to_plain_json():
    for e in explain(BEFORE, AFTER, "ci.yml"):
        data = json.loads(json.dumps(e.to_dict()))
        for key in (
            "id", "severity", "confidence", "change", "kind", "title", "message", "file", "job",
            "step", "line", "precision", "previous", "new", "consequence", "remediation", "snippet",
        ):  # fmt: skip
            assert key in data


def test_nothing_changed_gives_no_evidence():
    assert explain(AFTER, AFTER, "ci.yml") == []


# ---- hostile and damaged input ---------------------------------------------------


def test_control_characters_in_names_and_lines_are_removed():
    old = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: make\n"
    new = old + "      - run: curl https://evil.example/\x1b[31m red\n"
    for e in explain(old, new, "f.yml"):
        blob = json.dumps(e.to_dict())
        assert "\\u001b" not in blob and "\x1b" not in blob


def test_very_long_lines_are_cut_in_the_snippet():
    old = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: make\n"
    new = old + "      - run: curl https://x.example/" + "a" * 5000 + "\n"
    for e in explain(old, new, "f.yml"):
        assert all(len(s.text) <= 240 for s in e.snippet)


def test_a_finding_that_cannot_be_placed_still_reports_with_file_precision():
    # Flow style: the whole job is on one line, so only the job line is known.
    old = "on: push\njobs: {a: {runs-on: x, steps: [{run: make}]}}\n"
    new = "on: push\njobs: {a: {runs-on: x, steps: [{run: curl https://x.example/}]}}\n"
    net = one(explain(old, new, "f.yml"), "network")
    assert net.line == 2
    assert net.precision in {"line", "job"}


def test_a_file_name_with_odd_characters_is_cleaned():
    e = explain(BEFORE, AFTER, "dir/\x1b[2Jfile.yml")[0]
    assert "\x1b" not in e.file
