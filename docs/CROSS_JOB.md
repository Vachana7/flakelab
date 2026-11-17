# Powers that move between jobs

Status: **same-job combinations implemented** in version 0.5 (17 Nov 2026,
`pipedelta/jobs.py` and `pipedelta/paths.py`). Data passed from one job to
another is still not followed.

## The problem

Until version 0.5 PipeDelta decided whether a power was new by asking "did
this workflow have it anywhere before?". A power that turned up in another
job was low ("already present in this workflow; now also in job X").

Steps in one job share a machine, a token and environment variables. Separate
jobs do not. So which job holds a power matters.

## What version 0.5 does

1. `job_facts()` makes one record per job: stored secrets, outside addresses,
   unpinned outside actions, what the token can write, outsider text in a
   command, hidden decoded commands, own machine.
2. `paths_in()` lists every dangerous pairing inside a job from a fixed table
   (a way in or out, plus a secret or a write token).
3. A pairing is identified by its parts, for example
   (address stats.example.org, secret DEPLOY_KEY). The job name is not part of
   it. `new_paths()` returns pairings that no job had before the change.
4. `compare()` raises the finding for the part that arrived to the pairing's
   level and adds a sentence saying what it now sits next to. No finding is
   added and none is lowered.

| Change | Before 0.5 | Version 0.5 |
| --- | --- | --- |
| A secret moves into a job that already contacts an outside address | low | high |
| A secret moves into a job that pastes outsider text into a command | low | high |
| A secret moves onto a self-hosted runner | low | medium |
| An unpinned outside action moves into a job whose token can write | low | high |
| A power leaves one job but stays in another | nothing | a reduction note |

These five are tests in `tests/test_cross_job.py`. They were expected
failures until version 0.5; the markers were removed when they passed and the
test bodies were not changed. Three control tests in the same file (rename,
move between equally exposed jobs, copy into an equally exposed job) still
pass. `tests/test_paths.py` has the tests for the new modules.

## What it still does not do

**Do not claim that PipeDelta follows data between jobs.** It only looks at
what one job holds.

- A pairing is new only if it existed in no job. If a secret sat beside an
  address in job A and beside an injection in job C, moving it into job B
  that has both is low, because both pairings existed before.
- A secret moving from a read-only-token job to a write-token job with no way
  in (no address, outside code or outsider text) is low. So is a move into a
  job whose permissions cannot be worked out: an unknown token is never
  assumed to be able to write.
- A secret in a workflow that runs on `pull_request_target` is not a pairing,
  because the danger depends on whether the job checks out the outsider's
  code, which is not detected.
- Pairings that are not in the table are not seen.
- `if:` conditions: two jobs with the same facts and different guards look the same.
- Values passed between jobs through outputs, artifacts or caches, and
  anything in another file.
- It says what the file makes possible. It does not show that a secret is
  actually sent anywhere.

## Effect on real history

No attack case changed level. Of 1,659 real workflow commits, nine went up
to high (eight from medium, one from low) and none went down: 149 blocked
became 158. All nine are a secret arriving in a job beside unpinned outside
code (seven), an outside address (one) or outsider text in a command (one).
Nobody has judged whether those alerts were wanted, so this is alert volume
and not accuracy.

## Designs compared

Three candidate models were prototyped in a scratch script and run on ten
scenarios. The cell is the highest level each would report.

| Scenario | Should be | Before 0.5 | Subset, yes/no facts | Subset, concrete facts | Combination instances |
| --- | --- | --- | --- | --- | --- |
| Two earlier holders, one talks to a trusted host; secret added to a job that talks to a new host | high | low | low | high | high |
| Secret was beside an address in job A and an injection in job C; now in job B with both | debatable | low | high | high | low |
| Moves into two jobs: one talks out, one quiet | high | low | high | high | high |
| Job renamed only | low | low | low | low | low |
| Read-only-token job to write-all job, nothing else | judgement | low | medium | medium | low |
| Into a job whose permissions are unknown | judgement | low | medium | medium | low |
| Secret added to a file that already runs on pull_request_target | high | medium | high | high | high |
| Leaves one job, stays in another | low plus a note | none | none | none | low |
| Copied into an equally exposed job | low | low | low | low | low |
| Same address as before, plus an unpinned outside action | high | low | high | high | high |

- **Subset, yes/no facts** (low if some earlier holder had every kind of fact
  the new job has): rejected. Any earlier holder that contacts some address
  excuses every new address (first row).
- **Subset, concrete facts** (same, with specific addresses and actions):
  workable and the more cautious option. Harder to explain, depends on
  unrelated jobs, and raises findings for a secret beside a broader token
  with no way in.
- **Combination instances** (chosen): list each dangerous pairing inside
  a job, keyed by its members and not by the job name, for example
  (secret + address, DEPLOY_KEY, stats.example.org). Pairings present after
  and absent before are new; the reverse are reductions. Renames need no
  special handling because the pairings do not change.

The choice between the last two should be made by running both over the
commit history and a labelled benchmark. That has not been done.

Version 0.5 implements combination instances. The comparison against the
concrete-subset model on a labelled benchmark has still not been done.
