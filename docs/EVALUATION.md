# Evaluation

Every number on this page is produced by the scripts in `evaluation/` and copied
from `evaluation/results/*.json` by `evaluation/write_report.py`.

There are three separate tests. They answer different questions and their numbers
must not be combined.

## Summary

| | Version 0.1 | Version 0.4 |
|---|---|---|
| Attack cases blocked at the default gate | 6 of 12 | 9 of 12 |
| Same, counting only cases where a workflow file changes | 6 of 10 | 9 of 10 |
| Real past workflow commits blocked at the default gate | 384 of 1659 (23.1%) | 155 of 1659 (9.3%) |

Version 0.4 is version 0.1 plus three rounds of changes, each kept in
`evaluation/results/`. Version 0.2 changed rules after the first test run (8 of 10
attack cases, 164 of 1659 commits). Version 0.3 fixed eight bugs from a code review
(`tests/test_bugfixes.py`; 8 of 10, 157 of 1659). Version 0.4 closed detection gaps
found in a second review (`tests/test_v04_rules.py`): actions stored in the repository,
`secrets['NAME']`, injection through `actions/github-script`, more ways of hiding a
command, addresses written without `https://` or only known at run time, self-hosted
machines chosen through a matrix, and container images.

Versions 0.2 and 0.4 were written **after** looking at earlier results. Rules for
cases 03 and 04 (v0.2) and case 10 (v0.4, addresses only known at run time) were
added because those cases were missed. So the later attack scores are not
independent evidence: the tool was adjusted to these cases. The fair statement is
that version 0.1, written before any testing, blocked 6 of 10. The history test
below is the check that these changes did not simply add noise.

## Test 1: reconstructed attack cases

Question: when a pipeline change follows a publicly described attack pattern, does
PipeDelta block it at the default setting (any high-level new power)?

The cases are in `evaluation/attacks/`. They are **reconstructions** written for
this project from public descriptions, with harmless placeholder addresses. They are
not the original malicious files, and twelve cases is a small set chosen by the
author of the tool. Each `case.json` names its source.

| Case | What it is | v0.1 | v0.4 |
|---|---|---|---|
| 01 | New workflow posts a named secret to an outside address (GhostAction 2025 shape) | blocked | blocked |
| 02 | New workflow sends named secrets over plain HTTP (GhostAction 2026 shape) | blocked | blocked |
| 03 | New workflow decodes and runs a hidden script (Megalodon 2026 shape) | missed (low) | blocked |
| 04 | Existing workflow changed to send every secret at once | missed (medium) | blocked |
| 05 | Workflow gains pull_request_target and checks out the visitor's code (the setup later abused by 'pwn request' attacks) | blocked | blocked |
| 06 | Attack on an already risky pull_request_target workflow | cannot see | cannot see |
| 07 | Workflow starts using an outside action by a movable version tag (the setup behind the tj-actions and trivy-action incidents) | blocked | blocked |
| 08 | Version tag of an already used outside action is moved to malicious code | cannot see | cannot see |
| 09 | Workflow pastes a pull request title into a shell command | blocked | blocked |
| 10 | Secret sent to an address that is not written in the file | missed (medium) | blocked |
| 11 | Workflow uploads the whole checkout, including the stored token, as a public artifact (ArtiPACKED shape) | missed (low) | missed (low) |
| 12 | Workflow token widened to write-all | blocked | blocked |

What the misses mean:

- **Cases 06 and 08** cannot be seen at all. The attack happens without any change
  to the victim's workflow file. PipeDelta can only flag the earlier change that
  created the weakness (cases 05 and 07).
- **Case 10** is blocked since v0.4: a request whose address is only known at run
  time, in a job that reads a secret, is treated like a new address. This rule was
  written after seeing the miss.
- **Case 11** is missed by PipeDelta's own rules: it has no rule about what an
  artifact upload contains. zizmor catches it (see Test 3), which is why the two are
  meant to be used together.

## Test 3: the same cases with zizmor and poutine

Question: on the same changes, do established scanners raise a **new** top-level
problem? Each tool scans the file before and after the change; a problem that was
already there before does not count, because the reviewer would not see it as new.
zizmor counts when it reports a new result of severity High; poutine when it reports
a new result at level error or warning (its two highest). Both run with their default
settings. Versions: zizmor 1.32.0; poutine 1.1.6 built from source
(`go install`). zizmor ran with `--offline`, so its online audits were not used.

| Case | PipeDelta 0.4 | zizmor | poutine | PipeDelta + zizmor |
|---|---|---|---|---|
| 01 | blocked | missed | missed | blocked |
| 02 | blocked | flagged | missed | blocked |
| 03 | blocked | missed | missed | blocked |
| 04 | blocked | missed | flagged | blocked |
| 05 | blocked | flagged | missed | blocked |
| 06 | cannot see | cannot see | cannot see | cannot see |
| 07 | blocked | flagged | missed | blocked |
| 08 | cannot see | cannot see | cannot see | cannot see |
| 09 | blocked | flagged | flagged | blocked |
| 10 | blocked | missed | missed | blocked |
| 11 | missed | flagged | missed | blocked |
| 12 | blocked | missed | missed | blocked |
| **Total** | **9 of 12** | **5 of 12** | **2 of 12** | **10 of 12** |

How to read this:

- **This test favours PipeDelta.** The cases were written by PipeDelta's author, and
  PipeDelta's rules were later adjusted to them. zizmor and poutine were not. The
  numbers show *what kind* of change each tool notices, not which tool is better.
- The pattern is clear even so. zizmor and poutine look for **known weak patterns**
  (movable versions, template injection, dangerous triggers). They do not ask whether
  a change **starts sending a secret somewhere new**, which is how the 2025 and 2026
  secret-theft campaigns worked (cases 01, 02, 03, 10). PipeDelta does ask that.
- zizmor sees things PipeDelta does not (case 11, a token leaked through an artifact).
  PipeDelta's `--zizmor on` mode runs zizmor on both versions, keeps only its new
  results and explains them in the same plain language. Together they block
  10 of 12.

## Test 2: real workflow history of eight projects

Question: how often would PipeDelta have interrupted maintainers of real projects?

The script replayed every non-merge commit that touched `.github/workflows/` in
eight well-known Python projects (1663 commits), comparing each commit with its
parent. Only git history was read; no project code was run. 4 commits were
skipped because a workflow file was not valid YAML at that point.

| Project | Commit studied up to | Workflow commits | No new power | Low | Medium | High (blocked) |
|---|---|---|---|---|---|---|
| flask | `49943b5a94` | 99 | 42 | 50 | 3 | 4 |
| requests | `3c7baaa05a` | 107 | 38 | 60 | 2 | 7 |
| httpx | `b5addb64f0` | 28 | 18 | 8 | 2 | 0 |
| rich | `3a109ccdff` | 123 | 88 | 20 | 5 | 10 |
| black | `cf3e093897` | 277 | 94 | 158 | 10 | 13 |
| pydantic | `560f0f96a3` | 423 | 224 | 137 | 19 | 41 |
| pytest | `fc9a7ef678` | 255 | 95 | 138 | 5 | 17 |
| fastapi | `5758a9c834` | 351 | 143 | 126 | 19 | 63 |
| **Total** | | 1663 | 742 | 697 | 65 | 155 |

At the default setting PipeDelta 0.4 would have blocked 155 of 1659 commits
(9.3%). Version 0.1 blocked 384 (23.1%); most of the
difference came from no longer treating a version bump of an action already in use,
or a renamed job, as a new power. The new rules in version 0.4 did not raise the
block rate (version 0.3: 157).

The same commits judged by zizmor's new results (a new High result counts as a
block): zizmor alone 517 of 1659 (31.2%); PipeDelta with
`--zizmor on` 213 of 1659 (12.8%). zizmor alone is much
noisier mainly because it flags every version bump of an action that is not locked
to a commit, which PipeDelta treats as no new power. Because `--zizmor on` adds
interruptions, it is off by default.

Why the blocked commits were blocked (counted per high-level finding, version 0.4):

| Reason | Findings |
|---|---|
| outside action not locked to a commit | 250 |
| write permission | 101 |
| trigger pull_request_target | 14 |
| secret and new network address in the same job | 12 |
| trigger workflow_run | 4 |
| trigger issue_comment | 3 |
| injection | 2 |

How to read this:

- These commits are **not labelled**. Nobody has checked which of them were
  actually risky, so this is a block rate, not a false-alarm rate. None of them is
  a known attack.
- The largest reason is a new outside action referenced by a movable tag. Research
  papers call that a misconfiguration, so many of these blocks are arguably
  correct. They are still interruptions that maintainers of these projects did not ask for.
- About one workflow change in ten being blocked is probably too many for a
  required check on a busy project. A realistic use today is as a comment that
  informs the reviewer (`fail-on: never`), with blocking reserved for teams that
  already lock their actions to commits.

## What has not been done

- No comparison against scanners on cases written by someone else (Test 3 uses
  PipeDelta's own cases).
- No test on original malicious workflow files.
- No manual labelling of the blocked commits.
- Only Python projects were studied.
- No measurement of whether the plain-language sentences help a human reviewer.

## Reproduce

    pip install -e .
    pip install zizmor && go install github.com/boostsecurityio/poutine@v1.1.6
    python evaluation/run_attacks.py evaluation/results/attacks-v0.4.json
    python evaluation/run_comparison.py evaluation/results/comparison-v0.4.json
    git clone --no-checkout https://github.com/pallets/flask /tmp/hist/flask   # and the others
    python evaluation/run_history.py evaluation/results/history-v0.4.json /tmp/hist/*
    python evaluation/write_report.py

The version 0.1 result files were produced by commit `6492d9f`, the version 0.2 files by commit `2666b68` and the version 0.3 files by commit `594e8ec`.
