# Powers that move between jobs

Status: **same-job combinations implemented** in version 0.5 (17 Nov 2026,
`pipedelta/jobs.py` and `pipedelta/paths.py`). Of the ways data passes from
one job to another, only job outputs carrying outsider text are followed
(`pipedelta/links.py`).

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

## Values passed between jobs (job outputs)

Added on 17 Nov 2026 in `pipedelta/links.py`. Jobs run on separate machines.
The one hand-over this tool follows is a job output: job `a` publishes
`outputs: title: ...`, job `b` lists `needs: a` and reads
`needs.a.outputs.title`.

What is reported: outsider-controlled text that is published as an output and
pasted into a command (a `run:` script or a github-script `script:`) in a job
that needs it. That job then counts as pasting outsider text into a command,
so the same-job pairings above apply to it (beside a secret, beside a write
token). A change in job `a` can therefore raise a finding in job `b` that
nobody edited. Examples: `examples/outputs-before.yml`, `outputs-attack.yml`,
`outputs-safe.yml`.

An output is said to carry outsider text only when the file shows it:

1. its value names an outsider-controlled field directly;
2. its value is the output of a `run` step in the same job, and that step has
   outsider text in its command or in its own `env`;
3. its value is an output of another needed job that carries outsider text.

What is deliberately not assumed (each has a test in `tests/test_links.py`):

- `needs` alone passes nothing.
- A job reads only the outputs of jobs it lists under `needs` itself.
- An output the publishing job does not define is empty.
- GitHub withholds an output whose value contains a secret, so a secret is
  never said to arrive in the reading job through an output.
- An output filled by an action, a file or the network is left alone, because
  the workflow file does not show what is in it.
- Reading the output through an environment variable, or only comparing it,
  is not reported.

Limits of this part:

- Rule 2 is a guess in one direction: a step that handles outsider text and
  sets an output is assumed to put that text in the output. It may not.
- A secret that a step alters (for example encodes) before writing it to an
  output is not withheld by GitHub and is not seen by PipeDelta.
- Outsider text in a job-level or workflow-level `env` that a step copies to
  an output is not seen.
- Artifacts, caches and outputs of reusable workflows are not followed.

Evidence: 22 tests. On the evaluation it changed nothing: the attack cases
and all 1,659 history commits give identical results. In the latest workflow
files of the eight projects, 10 of 68 read a job output and none pastes one
into a command. So this feature is tested but has not been seen firing on
real history.

## Values passed between steps of one job (step outputs)

Added on 17 Nov 2026 in `pipedelta/stepflows.py`, as a separate commit after
the job-output work. It is the same idea inside one job: step `read` (with an
`id`) writes `title=...` to `$GITHUB_OUTPUT`, and a LATER step pastes
`steps.read.outputs.title` into a command. Examples:
`examples/steps-before.yml`, `steps-attack.yml`, `steps-safe.yml`.

A flow is reported only when the file shows every link:

1. the later step pastes the output into a `run` script or a github-script
   `script` (comparing it, or reading it through `env`, is not reported);
2. the source step is earlier in the same job;
3. the source step is a `run` step that writes to `$GITHUB_OUTPUT` or uses
   `::set-output`;
4. the line that writes THAT output carries outsider text: an outsider field
   pasted directly, a shell variable that the step's `env` (or an earlier
   line) filled with one, or an output that itself carries outsider text.

A step with several outputs is judged output by output. A value that comes
from a command, a file or an outside action is unknown and not accused.

The report gives the evidence: which step takes which field, which output it
sets, and which later step pastes it. A flow raises the same finding as any
other outsider text in a command, so the same-job pairings apply (beside a
secret, beside a write token).

Limits of this part (each is a documented miss, not tested as detected):

- Outsider text that reaches a step only through a job-level or
  workflow-level `env`.
- An output name built at run time, or a script that builds the whole
  `name=value` text in one variable.
- For the multi-line form (`name<<EOF`) the output is accused if the step
  handles outsider text anywhere, which can over-report.
- If the workflow already has the same flow in one job, a copy in a second job
  is rated low ("already present"). This is the existing rule for every kind
  of injection, not specific to steps.
- Job outputs (above) use a coarser rule: a `run` step that handles outsider
  text and is named by the job output is assumed to put it there.

Evidence: 34 tests. On the evaluation it changed nothing: the attack cases
and all 1,659 history commits give identical results. In the latest workflow
files of the eight projects, 23 of 68 read a step output and none carries
outsider text into a command, so this feature has not been seen firing on
real history.

## What it still does not do

**Do not claim that PipeDelta follows data between jobs in general.** It
looks at what one job holds, plus outsider text arriving through a job output.

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
- Values passed between jobs through artifacts or caches, secrets passed
  through outputs in altered form, and anything in another file.
- It says what the file makes possible. It does not show that a secret is
  actually sent anywhere.

## Effect on real history

No attack case changed level. Of 1,659 real workflow commits, nine went up
to high (eight from medium, one from low) and none went down: 149 blocked
became 158. All nine are a secret arriving in a job beside unpinned outside
code (seven), an outside address (one) or outsider text in a command (one).

A fix made afterwards in the same version (a login in front of a host is no
longer read as the host) made one more address visible. One more commit went
from medium to high: 159. In that commit a secret used as the login for
github.com was replaced by a differently named secret, so the pairing is new
by name although the workflow does the same thing as before.

Nobody has judged whether those ten alerts were wanted, so this is alert
volume and not accuracy.

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
