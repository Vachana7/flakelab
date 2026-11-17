"""Values passed from one step to a LATER step of the same job.

What GitHub does (docs: "Workflow commands" and the steps context):

* a step with an ``id`` can write ``name=value`` to the file named by
  ``$GITHUB_OUTPUT`` (or use the older ``::set-output``);
* a later step reads it as ``steps.<id>.outputs.<name>``;
* pasting ``${{ ... }}`` into a ``run:`` script substitutes the text BEFORE
  the shell starts, so the text becomes shell code.

What PipeDelta follows: outsider-controlled text that one step puts into an
output, and a later step of the same job that pastes that output into its
command (or into a github-script ``script``).

What these tests insist on NOT being assumed:

* a step output is not dangerous by itself;
* a step that handles outsider text does not make outputs it never writes
  dangerous;
* an output filled by an action cannot be read from the file;
* reading the output through ``env:`` is the safe way and is not reported.
"""

from pipedelta.stepflows import flows_in

from pipedelta.delta import compare, overall
from pipedelta.paths import paths_in
from pipedelta.powers import extract_powers

TOP = "on: pull_request\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n"

SOURCE = (
    "      - id: read\n"
    "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
    '        run: echo "title=$TITLE" >> "$GITHUB_OUTPUT"\n'
)
SOURCE_SAFE = '      - id: read\n        run: echo "title=$GITHUB_SHA" >> "$GITHUB_OUTPUT"\n'
SINK = '      - run: echo "${{ steps.read.outputs.title }}"\n'


def job(*steps: str, head: str = "") -> str:
    return TOP + head + "    steps:\n" + "".join(steps)


def from_step(text: str) -> set[str]:
    """Jobs in which an earlier step's output is pasted into a command."""
    return {
        p.where for p in extract_powers(text) if p.kind == "injection" and "earlier step" in p.name
    }


# ---- attack workflows -------------------------------------------------------


def test_outsider_text_through_env_and_output_file_reaches_a_later_command():
    assert from_step(job(SOURCE, SINK)) == {"a"}


def test_source_that_pastes_the_title_straight_into_its_own_command():
    source = (
        "      - id: read\n"
        '        run: echo "title=${{ github.event.pull_request.title }}" >> "$GITHUB_OUTPUT"\n'
    )
    assert from_step(job(source, SINK)) == {"a"}


def test_older_set_output_command():
    source = (
        "      - id: read\n"
        "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
        '        run: echo "::set-output name=title::$TITLE"\n'
    )
    assert from_step(job(source, SINK)) == {"a"}


def test_multi_line_output_with_a_delimiter():
    source = (
        "      - id: read\n"
        "        env:\n          BODY: ${{ github.event.pull_request.body }}\n"
        "        run: |\n"
        '          echo "body<<EOF" >> "$GITHUB_OUTPUT"\n'
        '          echo "$BODY" >> "$GITHUB_OUTPUT"\n'
        '          echo "EOF" >> "$GITHUB_OUTPUT"\n'
    )
    sink = '      - run: echo "${{ steps.read.outputs.body }}"\n'
    assert from_step(job(source, sink)) == {"a"}


def test_script_of_a_github_script_step():
    sink = (
        "      - uses: actions/github-script@v7\n"
        "        with:\n          script: console.log('${{ steps.read.outputs.title }}')\n"
    )
    assert from_step(job(SOURCE, sink)) == {"a"}


def test_all_outputs_of_the_step_at_once():
    sink = "      - run: echo '${{ toJSON(steps.read.outputs) }}'\n"
    assert from_step(job(SOURCE, sink)) == {"a"}


def test_other_spellings_of_the_same_reference():
    assert from_step(job(SOURCE, "      - run: echo \"${{ steps['read'].outputs['title'] }}\"\n"))
    assert from_step(job(SOURCE, '      - run: echo "${{ STEPS.READ.Outputs.TITLE }}"\n'))


def test_the_value_is_passed_on_through_a_middle_step():
    """Step two reads the output through env (safe on its own) and writes it to a new output."""
    middle = (
        "      - id: copy\n"
        "        env:\n          T: ${{ steps.read.outputs.title }}\n"
        '        run: echo "again=$T" >> "$GITHUB_OUTPUT"\n'
    )
    sink = '      - run: echo "${{ steps.copy.outputs.again }}"\n'
    assert from_step(job(SOURCE, middle, sink)) == {"a"}


def test_the_sink_does_not_have_to_come_straight_after_the_source():
    filler = "      - run: make\n"
    assert from_step(job(SOURCE, filler, filler, SINK)) == {"a"}


def test_evidence_names_the_source_the_output_and_both_steps():
    flows = flows_in(job(SOURCE, "      - run: make\n", SINK))
    assert len(flows) == 1
    flow = flows[0]
    assert (flow.job, flow.source_step, flow.output) == ("a", "read", "title")
    assert flow.origin == "github.event.pull_request.title"
    assert (flow.source_position, flow.sink_position) == (1, 3)
    assert flow.reference == "steps.read.outputs.title"


def test_the_report_shows_the_evidence():
    old = job(SOURCE_SAFE, SINK)
    new = job(SOURCE, SINK)
    raised = [f for f in compare(old, new) if f.power.kind == "injection"]
    assert [f.level for f in raised] == ["high"]
    message = raised[0].message
    assert "job 'a'" in message
    assert "github.event.pull_request.title" in message
    assert "steps.read.outputs.title" in message
    assert "step 1" in message and "step 2" in message


def test_one_edit_to_the_source_step_makes_an_untouched_later_step_dangerous():
    """The later step is identical before and after; only the source step changed."""
    secret = "    env:\n      K: ${{ secrets.DEPLOY_KEY }}\n"
    old = job(SOURCE_SAFE, SINK, head=secret)
    new = job(SOURCE, SINK, head=secret)
    assert overall(compare(old, new)) == "high"
    assert paths_in(old) == []
    assert "outsider commands can read a secret" in {p.rule for p in paths_in(new)}


# ---- safe workflows ---------------------------------------------------------


def test_reading_the_output_through_env_is_the_safe_way():
    sink = '      - env:\n          T: ${{ steps.read.outputs.title }}\n        run: echo "$T"\n'
    assert from_step(job(SOURCE, sink)) == set()


def test_an_output_nobody_outside_can_fill_is_not_reported():
    assert from_step(job(SOURCE_SAFE, SINK)) == set()


def test_a_step_that_handles_outsider_text_but_writes_a_different_output():
    """The title goes to ``title`` but the later step pastes ``sha``."""
    source = (
        "      - id: read\n"
        "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
        '        run: |\n          echo "title=$TITLE" >> "$GITHUB_OUTPUT"\n'
        '          echo "sha=$GITHUB_SHA" >> "$GITHUB_OUTPUT"\n'
    )
    sink = '      - run: echo "${{ steps.read.outputs.sha }}"\n'
    assert from_step(job(source, sink)) == set()


def test_a_step_that_handles_outsider_text_but_writes_no_output_at_all():
    source = (
        "      - id: read\n"
        "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
        '        run: echo "$TITLE" > title.txt\n'
    )
    assert from_step(job(source, SINK)) == set()


def test_reading_an_output_before_the_step_that_sets_it_runs():
    assert from_step(job(SINK, SOURCE)) == set()


def test_a_step_id_that_does_not_exist():
    assert from_step(job(SOURCE, '      - run: echo "${{ steps.other.outputs.title }}"\n')) == set()


def test_an_output_of_a_step_in_another_job_is_not_available():
    other = (
        "  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        '      - run: echo "${{ steps.read.outputs.title }}"\n'
    )
    assert from_step(job(SOURCE) + other) == set()


def test_an_output_filled_by_an_outside_action_is_unknown_and_not_accused():
    source = (
        "      - id: read\n        uses: someone/reader@v1\n"
        "        with:\n          text: ${{ github.event.pull_request.title }}\n"
    )
    assert from_step(job(source, SINK)) == set()


def test_an_output_that_is_only_compared_cannot_carry_text():
    sink = "      - run: echo ${{ steps.read.outputs.title == 'release' }}\n"
    assert from_step(job(SOURCE, sink)) == set()
    gated = "      - if: steps.read.outputs.title != ''\n        run: make\n"
    assert from_step(job(SOURCE, gated)) == set()


def test_a_name_that_only_looks_similar_is_not_the_output():
    """``title_long`` is written, ``title`` is read."""
    source = (
        "      - id: read\n"
        "        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
        '        run: echo "title_long=$TITLE" >> "$GITHUB_OUTPUT"\n'
    )
    assert from_step(job(source, SINK)) == set()


# ---- existing behaviour is preserved ----------------------------------------


def test_renaming_the_step_id_everywhere_reports_nothing():
    old = job(SOURCE, SINK)
    new = old.replace("id: read", "id: fetch").replace("steps.read.", "steps.fetch.")
    assert from_step(new) == {"a"}
    assert compare(old, new) == []


def test_renaming_the_job_reports_no_new_finding_above_low():
    old = job(SOURCE, SINK)
    new = old.replace("  a:\n", "  renamed:\n")
    assert [f for f in compare(old, new) if f.level != "low"] == []


def test_an_existing_flow_is_not_reported_again_after_an_unrelated_edit():
    old = job(SOURCE, SINK, "      - run: make\n")
    new = old.replace("- run: make\n", "- run: make all\n")
    assert compare(old, new) == []


def test_a_direct_paste_of_outsider_text_is_still_reported_as_before():
    text = job('      - run: echo "${{ github.event.pull_request.title }}"\n')
    assert {p.where for p in extract_powers(text) if p.kind == "injection"} == {"a"}
    assert from_step(text) == set()


def test_job_outputs_between_jobs_still_work_next_to_step_flows():
    text = (
        "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    outputs:\n      title: ${{ steps.read.outputs.title }}\n    steps:\n"
        + SOURCE
        + "  b:\n    runs-on: ubuntu-latest\n    needs: a\n    steps:\n"
        '      - run: echo "${{ needs.a.outputs.title }}"\n'
    )
    assert {p.where for p in extract_powers(text) if p.kind == "injection"} == {"b"}


# ---- damaged input and crafted input ----------------------------------------


def test_damaged_steps_do_not_crash():
    for steps in [
        "    steps: 5\n",
        "    steps:\n      - 7\n      - null\n",
        "    steps:\n      - id: [x]\n        run: 9\n",
        "    steps:\n      - id: read\n        env: [a, b]\n        run: echo\n",
        "    steps:\n      - id: 5\n        run: echo $GITHUB_OUTPUT\n",
        '    steps:\n      - id: read\n        env: {T: 3}\n        run: echo "t=$T" >> $GITHUB_OUTPUT\n',
    ]:
        text = TOP + steps
        assert from_step(text) == set()
        assert flows_in(text) == []


def test_a_job_that_is_not_a_mapping_does_not_crash():
    assert flows_in("on: push\njobs:\n  a: 5\n  b:\n    steps: x\n") == []
    assert flows_in("not: a workflow") == []
    assert flows_in("") == []


def test_a_very_long_chain_of_steps_is_read_quickly():
    import time

    steps = [SOURCE]
    for i in range(1, 1500):
        previous = "read" if i == 1 else f"s{i - 1}"
        name = "title" if i == 1 else "v"
        steps.append(
            f"      - id: s{i}\n"
            f"        env:\n          T: ${{{{ steps.{previous}.outputs.{name} }}}}\n"
            f'        run: echo "v=$T" >> "$GITHUB_OUTPUT"\n'
        )
    steps.append('      - run: echo "${{ steps.s1499.outputs.v }}"\n')
    started = time.time()
    assert from_step(job(*steps)) == {"a"}
    assert time.time() - started < 5
