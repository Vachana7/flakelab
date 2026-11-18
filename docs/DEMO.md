# Expo demo script

Total time: about 4 minutes. You need a browser logged in to GitHub. The
offline version at the bottom needs only a laptop with Docker.

Say the one-line idea first:

> "When someone changes a project's pipeline, my tool tells the reviewer what
> new powers the pipeline just gained, in plain words, before the change is
> accepted."

## Scene 1: an ordinary change passes (about 1 minute)

1. Open the repository on GitHub. Open `.github/workflows/ci.yml` and click the pencil (edit).
2. In the `matrix` line change `["3.10", "3.12"]` to `["3.10", "3.12", "3.13"]`.
3. Click **Commit changes**, choose **Create a new branch and start a pull request**, then **Propose changes** and **Create pull request**.
4. Wait about 40 seconds. The PipeDelta check turns green and its comment says the pipeline gained no new powers.

Say: "Testing on one more Python version changes the pipeline file, but gives it no new power. So it passes."

## Scene 2: a risky change is blocked (about 2 minutes)

1. Go back to the repository. Click **Add file → Create new file**.
2. Name it `.github/workflows/format.yml`.
3. Paste the contents of `examples/demo-paste.yml` (open it in another tab and copy).
4. Commit to a new branch and create the pull request, as in Scene 1.
5. Wait about 40 seconds. The PipeDelta check turns red and the comment lists the new powers.

Read two rows aloud and point at the matching lines in **Files changed**:

- "a command now contacts collector.example.invalid. The same job can read secrets, so they could be sent there."
- "now runs on pull_request_target, which people outside the project can set off."

Say: "This is the shape of real attacks from 2025 and 2026: someone adds a
small workflow that reads a secret and sends it away. A reviewer who is in a
hurry sees ten lines of YAML. My tool turns those ten lines into sentences."

Be honest if asked: the address and the action in the demo do not exist. It
is an imitation, and nothing is actually stolen.

## Scene 3: fix it and watch the report change (about 1 minute)

1. In the same pull request, open **Files changed**, click the three dots on `format.yml`, then **Edit file**.
2. Delete the last three lines (the `curl` line and the two `env` lines) and change the `on:` line to `on: [workflow_dispatch]`. Do not use `pull_request` here: that would make GitHub try to run the demo file itself.
3. Commit to the same branch.
4. Wait. The same comment updates itself: the secret, the internet address and
   the risky trigger are gone. The check is still red, because two high-level
   powers remain: the token can still change the repository, and the outside
   action is still not locked to a commit.

Say: "The comment is not a new one. The tool edits its earlier report, so the
reviewer always sees the current state. And it is still blocked, which is
correct: I removed the theft, but the pipeline still has more power than it needs."

## Scene 4 (optional, 1 minute): the attack that hides

Use this when an examiner asks "what if the attacker is smarter?". Run it in a
terminal (or `docker compose run --rm sneaky`):

    python -m pipedelta diff examples/before.yml examples/sneaky-workflow.yml
    python -m pipedelta diff - examples/sneaky-action.yml

Say: "Here the workflow change looks like a harmless refactor: the setup steps
moved into a shared action in the repository. The first line is all the reviewer
sees in the workflow. But PipeDelta also reads the new action file, and there it
finds a decoded hidden command and a new internet address. An earlier version of my
tool missed exactly this, which I found in a code review and fixed."

## Scene 5 (optional, 1 minute): a second opinion from zizmor

    python -m pipedelta diff examples/before.yml examples/after-artifact.yml --zizmor on

Say: "My own rules miss this one: uploading the whole folder leaks the token that
checkout stored. zizmor, an established scanner, catches it. PipeDelta runs zizmor
on the old and new file, keeps only what is new, and explains it in the same plain
words. Where both tools agree, the report says so."

## After the demo: reset

Close both pull requests without merging and delete their branches (GitHub
shows a **Delete branch** button after closing). Never merge the demo pull
requests.

## If the internet is down: offline version

Run these in the repository folder. Build once before the expo while you have internet.

    docker compose build
    docker compose run --rm safe
    docker compose run --rm attack
    docker compose run --rm fixed

`safe` prints one low-level power and passes. `attack` prints five high-level
powers and stops with an error. `fixed` prints one medium-level power and passes.

Pull request #2 in the repository is also kept as a ready-made example in case
there is no time to create one live.

## Questions an examiner is likely to ask

**Where is Docker used?** The tool is packaged as a Docker image. GitHub
builds and runs that image for every pull request, the pipeline tests the
image, and it is published to GitHub's container registry. The offline demo
uses Docker Compose.

**Where is CI/CD used?** Two workflows. `ci.yml` tests the code on two Python
versions, builds the image, checks the image against the examples, and
publishes it. `pipedelta.yml` runs the tool on this repository's own pull
requests.

**Can an attacker just delete your check in the same pull request?** Yes,
unless the repository owner marks the check as required in branch settings.
This is written in the README under known limits.

**Does it catch every attack?** No. It reads workflow files and the actions
stored in the repository, but not outside actions or scripts that a step runs. An
address built from variables is reported only as "known at run time". Attacks that
change no file, such as a hijacked version tag, cannot be seen by any tool of this
kind. It is meant to help a human reviewer, not replace one.

**Can a pull request add itself to the trust list?** No. The trust list
(`.pipedelta.yml`) is read from the target branch, not from the pull request, and a
pull request that widens it is reported.

**How is it different from existing scanners such as zizmor?** zizmor and
poutine look for known weak patterns in a workflow as it is. PipeDelta reports
what a change added, in plain sentences, and combines signals: a secret and a new
address in the same job. I ran all three on the same 12 cases, counting only
problems that are new in the change: PipeDelta 9, zizmor 5, poutine 2, PipeDelta
with zizmor 10. Say straight away that the cases are mine, so the test favours my
tool; the useful finding is that zizmor and poutine do not flag the secret-theft
cases (01, 02, 03, 10), while zizmor catches one PipeDelta misses (11). That is why
PipeDelta can run zizmor as a second opinion.

**How do you know the levels are right?** They are hand-written rules, and I
measured them three ways (`docs/EVALUATION.md`). On 12 attack cases that I
reconstructed from public reports, the first version blocked 6 of the 10 where
a workflow file changes; after I added rules for the misses it blocks 9, but
that number is not independent because I adjusted the tool to those cases. On
1,659 real past workflow commits from eight Python projects, it would have
blocked about one in eleven, mostly for outside actions that were not locked to a
commit; zizmor alone would have raised a new High result on about one in three.
For teams that do not lock actions yet, a trust list or comment-only mode fits better.

**What would you do next?** Test on workflow files written by someone else (for
example zizmor's own test cases), label a sample of the blocked commits by hand
to get a real false-alarm rate, and follow scripts that a step runs.
