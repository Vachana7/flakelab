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
2. Delete the last three lines (the `curl` line and the two `env` lines) and change `pull_request_target` to `pull_request`.
3. Commit to the same branch.
4. Wait. The same comment updates itself: the secret, the internet address and
   the risky trigger are gone. The check is still red, because two high-level
   powers remain: the token can still change the repository, and the outside
   action is still not locked to a commit.

Say: "The comment is not a new one. The tool edits its earlier report, so the
reviewer always sees the current state. And it is still blocked, which is
correct: I removed the theft, but the pipeline still has more power than it needs."

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

**Does it catch every attack?** No. It reads workflow files only. It does not
look inside the outside actions a workflow calls, and it misses addresses
built from variables. It is meant to help a human reviewer, not replace one.

**How is it different from existing scanners such as zizmor?** Those tools
report problems in a workflow file as it is. PipeDelta reports what a change
added, in plain sentences. They can be used together. I have not found a tool
that reports changes this way, but I cannot say for certain that none exists.

**How do you know the levels are right?** They are hand-written rules. See
`docs/EVALUATION.md` for how they did on known attack patterns and on ordinary
changes from real projects. (Written on Day 4. Until then, say it has not been
measured yet.)
