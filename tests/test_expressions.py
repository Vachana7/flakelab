"""How secrets and untrusted values are recognised inside ${{ ... }} expressions.

Written before the fix. Sources for the expected behaviour:
- GitHub Docs, "Evaluate expressions": "[ ]" (index) and "." (property
  de-reference) are both operators; strings use single quotes only.
- GitHub Docs, "Secrets": secret names "are case insensitive when
  referenced. GitHub stores secret names as uppercase".
- Whether CONTEXT names (secrets, github) are case-insensitive is NOT stated
  in the pages we could read. PipeDelta matches them without regard to case
  on purpose: if GitHub accepts the spelling we must see it, and if GitHub
  rejects it, reporting it is a harmless over-report.
"""

import pytest

from pipedelta.delta import compare, overall

BASE = """on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: make
"""


def with_env(expression: str) -> str:
    return BASE + f"        env:\n          K: {expression}\n"


def with_run(command: str) -> str:
    return BASE + f"      - run: {command}\n"


def secrets_found(new: str) -> set[str]:
    return {f.power.name for f in compare(BASE, new) if f.power.kind == "secret"}


def has_injection(new: str) -> bool:
    return any(f.power.kind == "injection" for f in compare(BASE, new))


# --- secrets: every documented way to write the same reference ---------------

SAME_SECRET = [
    "${{ secrets.DEPLOY_KEY }}",
    "${{secrets.DEPLOY_KEY}}",
    "${{ secrets.deploy_key }}",
    "${{ secrets.Deploy_Key }}",
    "${{ secrets['DEPLOY_KEY'] }}",
    "${{ secrets['deploy_key'] }}",
    "${{ secrets[ 'DEPLOY_KEY' ] }}",
    "${{ SECRETS.DEPLOY_KEY }}",
    "${{ Secrets['DEPLOY_KEY'] }}",
    "${{ format('{0}', secrets.DEPLOY_KEY) }}",
    "${{ secrets.DEPLOY_KEY || 'none' }}",
]


@pytest.mark.parametrize("expression", SAME_SECRET)
def test_every_spelling_of_one_secret_is_the_same_secret(expression):
    assert secrets_found(with_env(expression)) == {"DEPLOY_KEY"}


def test_two_spellings_of_one_secret_are_not_a_change():
    old = with_env("${{ secrets.DEPLOY_KEY }}")
    new = with_env("${{ SECRETS['deploy_key'] }}")
    assert [f for f in compare(old, new) if f.power.kind == "secret"] == []


RUN_TIME = [
    "${{ secrets[format('{0}_KEY', 'DEPLOY')] }}",
    "${{ secrets[matrix.secret_name] }}",
    "${{ secrets[inputs.which] }}",
]


@pytest.mark.parametrize("expression", RUN_TIME)
def test_secret_chosen_at_run_time_is_reported_not_dropped(expression):
    found = secrets_found(with_env(expression))
    assert len(found) == 1
    assert "run time" in next(iter(found))


@pytest.mark.parametrize(
    "expression", ["${{ toJSON(secrets) }}", "${{ toJson( SECRETS ) }}", "${{ secrets.* }}"]
)
def test_whole_secrets_object_means_every_secret(expression):
    found = secrets_found(with_env(expression))
    assert len(found) == 1
    assert "every secret" in next(iter(found))


def test_secret_in_an_if_condition_is_seen():
    new = BASE.replace(
        "      - run: make\n", "      - if: secrets.DEPLOY_KEY != ''\n        run: make\n"
    )
    assert secrets_found(new) == {"DEPLOY_KEY"}


def test_several_secrets_in_one_expression():
    assert secrets_found(with_env("${{ secrets.A || secrets['b'] }}")) == {"A", "B"}


# --- secrets: things that must NOT be reported -------------------------------

NOT_A_SECRET = [
    "plain text mentioning secrets.DEPLOY_KEY outside an expression",
    "${{ 'secrets.DEPLOY_KEY' }}",
    "${{ vars.DEPLOY_KEY }}",
    "${{ github.sha }}",
    "${{ needs.build.outputs.secrets }}",
    "${{ steps.x.outputs.secrets_ok }}",
    "${{ env.secrets }}",
]


@pytest.mark.parametrize("text", NOT_A_SECRET)
def test_these_are_not_secret_references(text):
    assert secrets_found(with_env(text)) == set()


# --- injection: every spelling of an untrusted value in a command -------------

INJECTED = [
    'echo "${{ github.event.pull_request.title }}"',
    'echo "${{github.event.issue.title}}"',
    'echo "${{ GitHub.Event.Pull_Request.Title }}"',
    "echo \"${{ github['event']['pull_request']['title'] }}\"",
    "echo \"${{ github.event['issue'].title }}\"",
    "echo \"${{ format('{0}', github.event.issue.title) }}\"",
    'echo "${{ toJSON(github.event.comment.body) }}"',
    'echo "${{ github.head_ref }}"',
    'echo "${{ GITHUB.HEAD_REF }}"',
    "echo \"${{ github.event.issue.title || 'none' }}\"",
]


@pytest.mark.parametrize("command", INJECTED)
def test_untrusted_value_in_a_command_is_an_injection_however_it_is_spelt(command):
    new = with_run(command)
    assert has_injection(new)
    assert overall(compare(BASE, new)) == "high"


def test_untrusted_value_inside_a_github_script_step_is_an_injection():
    new = BASE + (
        "      - uses: actions/github-script@v7\n"
        "        with:\n"
        '          script: console.log("${{ github.event.issue.title }}")\n'
    )
    assert has_injection(new)


# --- injection: things that must NOT be reported -----------------------------

SAFE = [
    'echo "${{ github.sha }}"',
    'echo "${{ github.repository }}"',
    'echo "${{ github.event_name }}"',
    'echo "${{ runner.os }}"',
    "echo github.event.issue.title is only text here",
    "echo \"${{ 'github.event.issue.title' }}\"",
    'echo "${{ steps.x.outputs.title }}"',
]


@pytest.mark.parametrize("command", SAFE)
def test_these_commands_are_not_injections(command):
    assert not has_injection(with_run(command))


def test_the_recommended_safe_pattern_is_not_an_injection():
    # Untrusted value goes into an environment variable, the shell reads the variable.
    new = (
        BASE
        + '      - run: echo "$TITLE"\n        env:\n          TITLE: ${{ github.event.issue.title }}\n'
    )
    assert not has_injection(new)


def test_untrusted_value_in_a_step_name_is_not_an_injection():
    new = BASE.replace(
        "      - run: make\n",
        "      - name: Title ${{ github.event.issue.title }}\n        run: make\n",
    )
    assert not has_injection(new)


def test_github_script_reading_the_environment_is_not_an_injection():
    new = BASE + (
        "      - uses: actions/github-script@v7\n"
        "        env:\n          TITLE: ${{ github.event.issue.title }}\n"
        "        with:\n          script: console.log(process.env.TITLE)\n"
    )
    assert not has_injection(new)


# --- false alarms found in the final review -----------------------------------


def test_property_named_secrets_on_another_object_is_not_a_secret():
    assert secrets_found(with_env("${{ fromJSON(env.CONFIG).secrets.KEY }}")) == set()


def test_property_named_github_on_another_object_is_not_an_injection():
    assert not has_injection(with_run('echo "${{ fromJSON(env.C).github.event.issue.title }}"'))


COMPARED_ONLY = [
    "echo \"${{ github.event.pull_request.draft == true && 'a' || 'b' }}\"",
    "echo \"${{ 'x' != github.event.issue.title && 'a' || 'b' }}\"",
    "echo \"${{ contains(github.event.pull_request.labels.*.name, 'x') }}\"",
    "echo \"${{ startsWith(github.head_ref, 'release/') }}\"",
    "echo \"${{ endsWith(github.event.issue.title, '!') && 'yes' || 'no' }}\"",
]


@pytest.mark.parametrize("command", COMPARED_ONLY)
def test_untrusted_value_that_is_only_compared_is_not_an_injection(command):
    # The text pasted into the command is true/false or a fixed string.
    assert not has_injection(with_run(command))


STILL_INSERTED = [
    "echo \"${{ github.event.issue.title || 'none' }}\"",
    "echo \"${{ github.event_name == 'issues' && github.event.issue.title || 'none' }}\"",
    "echo \"${{ format('{0}', github.event.issue.title) }}\"",
    "echo \"${{ format('{0} {1}', contains(github.head_ref, 'x'), github.event.issue.title) }}\"",
    'echo "${{ github.event.issue.title }} ${{ github.event.issue.number == 1 }}"',
]


@pytest.mark.parametrize("command", STILL_INSERTED)
def test_untrusted_value_that_can_reach_the_command_is_still_an_injection(command):
    assert has_injection(with_run(command))
