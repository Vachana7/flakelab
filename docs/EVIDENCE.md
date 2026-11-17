# Evidence for each finding

Every finding that PipeDelta reports carries the facts needed to check it in
the file. Code: `pipedelta/evidence.py`. Tests: `tests/test_evidence.py`.

| Field | Meaning |
| --- | --- |
| `severity` | How bad it would be if the capability were abused: low, medium, high. This is the level `compare()` decided. |
| `confidence` | How sure PipeDelta is that the file really gives this capability (below). |
| `file`, `job`, `step`, `line` | Where it is. Lines and steps count from 1. |
| `precision` | How exactly it could be placed: `line`, `job` (only the job's first line is known) or `file`. |
| `previous`, `new` | The value before and after. A new power has no previous value; a removed one has no new value. |
| `snippet` | The line and up to two lines either side, from the file itself. |
| `consequence`, `remediation` | Why it matters and what to do, in plain sentences. |
| `side` | `after` if the line is in the new file, `before` for a removed power (it is in the old file). |

## Confidence

- **high**: the file says it in so many words: a `uses:` line, a `secrets.X`
  reference, a URL, a `permissions:` entry.
- **medium**: PipeDelta inferred it by a rule. Today that means outsider text
  carried by an output from one step or job into another. The rule can be
  wrong in one direction: a step that handles outsider text and sets an output
  is assumed to put that text in it.
- **low**: the file does not say. For example a permission whose level cannot
  be read, so the repository default applies.

Confidence is about the finding being true of the file. It is not a
probability that an attacker exists, and it is not a measured accuracy.

## How lines are found

PyYAML's `compose` gives the position of every job and every step. For each
finding PipeDelta then looks, inside the right job (and, for commands, inside
the right steps), for the first line that contains the thing itself: the
secret name, the host, the `uses:` value, the untrusted expression. If the
thing cannot be found on a single line (for example the whole job is written
on one line, or an expression is split over several lines) the finding is
placed on the job's first line and `precision` says `job`.

## What it does not do

- It does not change any level. Levels come from `compare()`.
- A finding raised because of a combination (for example a secret beside an
  outside address) is placed on the part that arrived, not on both parts. The
  message names the other part.
- The consequence and remediation sentences are fixed wording per kind of
  finding. They describe the general risk, not a proof that this workflow is
  exploitable.
