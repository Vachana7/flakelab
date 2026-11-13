# Evaluation

Every number on this page is produced by the scripts in `evaluation/` and copied
from `evaluation/results/*.json` by `evaluation/write_report.py`.

There are two separate tests. They answer different questions and their numbers
must not be combined.

## Summary

| | Version 0.1 | Version 0.2 |
|---|---|---|
| Attack cases blocked at the default gate | 6 of 12 | 8 of 12 |
| Same, counting only cases where a workflow file changes | 6 of 10 | 8 of 10 |
| Real past workflow commits blocked at the default gate | 384 of 1659 (23.1%) | 164 of 1659 (9.9%) |

Version 0.2 was written **after** looking at the version 0.1 results. Two of its
rules (hidden decoded commands, and `toJSON(secrets)`) were added because cases 03
and 04 were missed. So the version 0.2 attack score is not independent evidence:
the tool was adjusted to those cases. The fair statement is that version 0.1,
written before any testing, blocked 6 of 10.

## Test 1: reconstructed attack cases

Question: when a pipeline change follows a publicly described attack pattern, does
PipeDelta block it at the default setting (any high-level new power)?

The cases are in `evaluation/attacks/`. They are **reconstructions** written for
this project from public descriptions, with harmless placeholder addresses. They are
not the original malicious files, and twelve cases is a small set chosen by the
author of the tool. Each `case.json` names its source.

| Case | What it is | v0.1 | v0.2 |
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
| 10 | Secret sent to an address that is not written in the file | missed (medium) | missed (medium) |
| 11 | Workflow uploads the whole checkout, including the stored token, as a public artifact (ArtiPACKED shape) | missed (low) | missed (low) |
| 12 | Workflow token widened to write-all | blocked | blocked |

What the misses mean:

- **Cases 06 and 08** cannot be seen at all. The attack happens without any change
  to the victim's workflow file. PipeDelta can only flag the earlier change that
  created the weakness (cases 05 and 07).
- **Case 10** is reported as medium, not blocked: the secret is seen but the
  address comes from a variable. This is the limit stated in the README.
- **Case 11** is missed: PipeDelta has no rule about what an artifact upload contains.

## Test 2: real workflow history of eight projects

Question: how often would PipeDelta have interrupted maintainers of real projects?

The script replayed every non-merge commit that touched `.github/workflows/` in
eight well-known Python projects (1663 commits), comparing each commit with its
parent. Only git history was read; no project code was run. 4 commits were
skipped because a workflow file was not valid YAML at that point.

| Project | Commit studied up to | Workflow commits | No new power | Low | Medium | High (blocked) |
|---|---|---|---|---|---|---|
| flask | `49943b5a94` | 99 | 42 | 50 | 2 | 5 |
| requests | `3c7baaa05a` | 107 | 38 | 62 | 0 | 7 |
| httpx | `b5addb64f0` | 28 | 18 | 9 | 1 | 0 |
| rich | `3a109ccdff` | 123 | 88 | 22 | 3 | 10 |
| black | `cf3e093897` | 277 | 93 | 163 | 2 | 17 |
| pydantic | `560f0f96a3` | 423 | 220 | 140 | 16 | 45 |
| pytest | `fc9a7ef678` | 255 | 96 | 136 | 6 | 17 |
| fastapi | `5758a9c834` | 351 | 144 | 124 | 20 | 63 |
| **Total** | | 1663 | 739 | 706 | 50 | 164 |

At the default setting PipeDelta 0.2 would have blocked 164 of 1659 commits
(9.9%). Version 0.1 blocked 384 (23.1%); most of the
difference came from no longer treating a version bump of an action already in use,
or a renamed job, as a new power.

Why the blocked commits were blocked (counted per high-level finding, version 0.2):

| Reason | Findings |
|---|---|
| outside action not locked to a commit | 272 |
| write permission | 103 |
| secret and new network address in the same job | 14 |
| trigger pull_request_target | 14 |
| trigger workflow_run | 6 |
| injection | 4 |
| trigger issue_comment | 3 |

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

- No comparison against existing scanners (zizmor, poutine) on the same cases.
- No test on original malicious workflow files.
- No manual labelling of the blocked commits.
- Only Python projects were studied.
- No measurement of whether the plain-language sentences help a human reviewer.

## Reproduce

    pip install -e .
    python evaluation/run_attacks.py evaluation/results/attacks-v0.2.json
    git clone --no-checkout https://github.com/pallets/flask /tmp/hist/flask   # and the others
    python evaluation/run_history.py evaluation/results/history-v0.2.json /tmp/hist/*
    python evaluation/write_report.py

The version 0.1 result files were produced by commit `6492d9f`.
