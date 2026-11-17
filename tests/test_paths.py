"""Per-job facts and same-job attack paths. Written before the implementation."""

from pipedelta.delta import compare, overall
from pipedelta.jobs import job_facts
from pipedelta.paths import new_paths, paths_in

HEAD = "on: push\npermissions:\n  contents: read\njobs:\n"
SECRET = "        env:\n          K: ${{ secrets.DEPLOY_KEY }}\n"
NET = "      - run: curl https://stats.example.org/up\n"
INJ = '      - run: echo "${{ github.event.pull_request.title }}"\n'
TOOL = "      - uses: someone/tool@v1\n"
WRITE = "    permissions:\n      contents: write\n"


def job(name, body="      - run: make\n", runner="ubuntu-latest", perms=""):
    return f"  {name}:\n    runs-on: {runner}\n{perms}    steps:\n{body}"


def rules(text):
    return {p.rule for p in paths_in(text)}


# --- JobFacts: what one job holds ---------------------------------------------


def test_job_facts_collects_what_each_job_holds():
    facts = job_facts(
        HEAD + job("a", NET + SECRET) + job("b", TOOL, runner="self-hosted", perms=WRITE)
    )
    a, b = facts["a"], facts["b"]
    assert a.secrets == {"DEPLOY_KEY"}
    assert a.hosts == {"stats.example.org"}
    assert not a.write_scopes
    assert b.secrets == set()
    assert b.unpinned == {"someone/tool"}
    assert b.self_hosted
    assert b.write_scopes == {"contents"}


def test_workflow_level_secret_belongs_to_every_job():
    text = "on: push\nenv:\n  K: ${{ secrets.DEPLOY_KEY }}\njobs:\n" + job("a") + job("b")
    facts = job_facts(text)
    assert facts["a"].secrets == facts["b"].secrets == {"DEPLOY_KEY"}


def test_built_in_token_is_not_counted_as_a_secret():
    text = HEAD + job(
        "a", "      - run: make\n        env:\n          T: ${{ secrets.GITHUB_TOKEN }}\n"
    )
    assert job_facts(text)["a"].secrets == set()


def test_unknown_token_is_not_assumed_to_be_able_to_write():
    assert job_facts("on: push\njobs:\n" + job("a"))["a"].write_scopes == set()


def test_pinned_and_github_owned_actions_are_not_unpinned_outside_code():
    body = "      - uses: actions/checkout@v4\n      - uses: someone/tool@" + "a" * 40 + "\n"
    assert job_facts(HEAD + job("a", body))["a"].unpinned == set()


# --- paths inside one job ------------------------------------------------------


def test_secret_and_outside_address_in_one_job_is_a_path():
    assert "secret can be sent out" in rules(HEAD + job("a", NET + SECRET))


def test_secret_in_one_job_and_address_in_another_is_not_a_path():
    assert rules(HEAD + job("a", "      - run: make\n" + SECRET) + job("b", NET)) == set()


def test_each_rule_fires_only_with_both_parts_in_the_same_job():
    assert "outsider commands can read a secret" in rules(HEAD + job("a", INJ + SECRET))
    assert "outside code can read a secret" in rules(HEAD + job("a", TOOL + SECRET))
    assert "outside code runs with a write token" in rules(HEAD + job("a", TOOL, perms=WRITE))
    assert "outsider commands run with a write token" in rules(HEAD + job("a", INJ, perms=WRITE))
    assert "secret on the project's own machine" in rules(
        HEAD + job("a", "      - run: make\n" + SECRET, runner="self-hosted")
    )
    assert rules(HEAD + job("a", TOOL + NET + INJ)) == set()  # nothing sensitive
    assert (
        rules(HEAD + job("a", "      - run: make\n" + SECRET, perms=WRITE)) == set()
    )  # no way in or out


def test_a_path_does_not_depend_on_the_job_name_or_order():
    one = HEAD + job("build", NET + SECRET) + job("other")
    renamed = HEAD + job("other") + job("compile", NET + SECRET)
    assert new_paths(one, renamed) == []
    assert new_paths(renamed, one) == []


def test_new_paths_lists_only_what_was_not_possible_before():
    old = HEAD + job("a", NET + SECRET) + job("b", INJ)
    new = HEAD + job("a", NET + SECRET) + job("b", INJ + SECRET)
    found = new_paths(old, new)
    assert [p.rule for p in found] == ["outsider commands can read a secret"]
    assert found[0].jobs == ("b",)


# --- effect on findings -------------------------------------------------------


def test_secret_added_to_a_job_that_already_contacts_an_address_is_high():
    old = HEAD + job("a", NET)
    findings = compare(old, HEAD + job("a", NET + SECRET))
    assert overall(findings) == "high"
    secret = next(f for f in findings if f.power.kind == "secret")
    assert "stats.example.org" in secret.message


def test_secret_added_to_a_job_with_unpinned_outside_code_is_high():
    assert overall(compare(HEAD + job("a", TOOL), HEAD + job("a", TOOL + SECRET))) == "high"


def test_secret_added_to_a_quiet_job_stays_medium():
    assert (
        overall(compare(HEAD + job("a"), HEAD + job("a", "      - run: make\n" + SECRET)))
        == "medium"
    )


def test_existing_path_is_not_reported_again_after_an_unrelated_edit():
    old = HEAD + job("a", NET + SECRET)
    new = HEAD + job("a", NET + SECRET + "      - run: make test\n")
    assert compare(old, new) == []


def test_existing_path_survives_a_version_bump_without_a_high_finding():
    old = HEAD + job("a", TOOL + SECRET)
    new = old.replace("someone/tool@v1", "someone/tool@v2")
    assert overall(compare(old, new)) == "low"


def test_reordering_jobs_reports_nothing():
    a, b = job("a", NET + SECRET), job("b", TOOL, perms=WRITE)
    assert compare(HEAD + a + b, HEAD + b + a) == []


def test_renaming_a_job_that_holds_a_path_is_not_high():
    old = HEAD + job("build", NET + TOOL + SECRET, perms=WRITE)
    assert overall(compare(old, old.replace("  build:", "  compile:"))) in ("none", "low")


def test_the_raised_finding_says_what_the_power_is_now_next_to():
    old = HEAD + job("a", "      - run: make\n" + SECRET) + job("b", INJ)
    new = HEAD + job("a") + job("b", INJ + SECRET)
    secret = next(f for f in compare(old, new) if f.power.kind == "secret" and f.change == "gained")
    assert secret.level == "high"
    assert "'b'" in secret.message
    assert "outsider" in secret.message
