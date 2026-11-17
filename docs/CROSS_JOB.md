# Known limitation: powers that move between jobs

Status: **not implemented**. Recorded on 16 Nov 2026. Deferred until after the expo.

## What happens today

PipeDelta decides whether a power is new by asking "did this workflow have it
anywhere before?". If the answer is yes, a power that turns up in another job
is reported as low ("already present in this workflow; now also in job X").

Steps in one job share a machine, a token and environment variables. Separate
jobs do not. So which job holds a power matters, and the tool does not look.

## Effect on findings

| Change | Reported today | Should be |
| --- | --- | --- |
| A secret moves into a job that already contacts an outside address | low | high |
| A secret moves into a job that pastes outsider text into a command | low | high |
| A secret moves onto a self-hosted runner | low | medium |
| An unpinned outside action moves into a job whose token can write | low | high |
| A power leaves one job but stays in another | nothing | a reduction note |

The first row is the tool's own headline rule (secret plus outside address)
failing when the secret is moved instead of added. A reviewer relying on the
level alone would let it through.

**Do not claim that PipeDelta detects cross-job capability movement.** It
reports the move, at low level, without saying what it is now next to.

These five cases are tests in `tests/test_cross_job.py`, marked as expected
failures. Three control tests in the same file (rename, move between equally
exposed jobs, copy into an equally exposed job) pass and must keep passing.

## Designs compared

Three candidate models were prototyped in a scratch script and run on ten
scenarios. The cell is the highest level each would report.

| Scenario | Should be | Today | Subset, yes/no facts | Subset, concrete facts | Combination instances |
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
- **Combination instances** (recommended): list each dangerous pairing inside
  a job, keyed by its members and not by the job name, for example
  (secret + address, DEPLOY_KEY, stats.example.org). Pairings present after
  and absent before are new; the reverse are reductions. Renames need no
  special handling because the pairings do not change.

The choice between the last two should be made by running both over the
commit history and a labelled benchmark. That has not been done.

## Planned shape

1. One record per job: effective token, secrets, addresses, outside code,
   runner, injection, hidden execution. (`Token` already exists.)
2. Per-job diff for display, jobs matched by name.
3. A fixed table of dangerous pairings evaluated inside each job.
4. Levels from the pairings that are new.

## What even the planned design will not see

- Pairings that are not in the table.
- `if:` conditions: two jobs with the same facts and different guards look the same.
- Values passed between jobs through outputs, and anything in another file.
