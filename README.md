# PipeDelta

PipeDelta reviews changes to GitHub Actions workflow files and reports, in plain
language, what new powers a pipeline gained: new secrets it can read, new
permissions, new triggers, new third-party actions, new network destinations.

Status (13 Nov 2026): the comparison, the Docker image, the GitHub Action and
the pull request comment work. A live example is pull request #2 in this
repository. A first evaluation is in `docs/EVALUATION.md`: it blocked 8 of 12
reconstructed attack cases (2 of the 12 are invisible to it by design) and
would have blocked about 1 in 10 real past workflow commits in eight Python
projects. A results page is in `dashboard/index.html` (open it in a browser).

## Use it in a repository

    # .github/workflows/pipedelta.yml
    on:
      pull_request:
        paths: [".github/workflows/**"]
    permissions:
      contents: read
      pull-requests: write
    jobs:
      review:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
            with:
              fetch-depth: 0
              persist-credentials: false
          # Replace with the full commit id of the PipeDelta version you reviewed.
          # Do not use a branch name such as @main: whoever can push to that
          # branch could then change what runs in your pipeline.
          - uses: Vachana7/pipedelta@<40-character commit id>
            with:
              token: ${{ github.token }}

## Try it

    pip install pyyaml
    python -m pipedelta diff examples/before.yml examples/after-attack.yml
    python -m pipedelta git <base-commit> <head-commit>

The command exits with an error when a change adds a high-level power, so a
pipeline can use it to block the change.

## The web app

Full Windows instructions, token setup, troubleshooting and a four-minute expo
quick start are in `docs/SETUP.md`. In short, in Windows PowerShell:

    git clone https://github.com/Vachana7/pipedelta.git
    cd pipedelta
    git checkout platform
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e .
    pipedelta serve                  # then open http://127.0.0.1:8765

On Linux or macOS use `source .venv/bin/activate` instead of the activate line.
A GitHub token is optional (public repositories work without one, at 60
requests per hour). Set it in the same terminal before starting, for example
`$env:GITHUB_TOKEN = "..."` in PowerShell, and never share it. The server only
answers on localhost. See `docs/PLATFORM.md` for the architecture.

## Documents

- `docs/FEATURES_GUIDE.md`, `docs/EXPO_PRESENTATION.md`, `docs/PROJECT_REPORT.md`: feature guide, presenting to experts, project report
- `docs/SETUP.md`: set up and run on Windows, token, troubleshooting, expo quick start
- `docs/PLATFORM.md`: the web app, API, security choices, expo walk-through
- `docs/EVIDENCE.md`: what each finding records

- `docs/DEMO.md`: expo demo script and likely examiner questions
- `docs/EVALUATION.md`: what was measured and what was not
- `docs/UX.md`: personas, user journey, wireframes
- `docs/LEARN.md`: study notes with questions

## Known limits

- **Only what one job holds is combined.** A new power is rated by what it
  sits next to in its own job (a secret beside an outside address, outsider
  text or unpinned outside code; outside code or outsider text beside a write
  token). Outsider-controlled text is also followed when it is published as
  a job output and pasted into a command by a job that needs it, or written
  to a step output and pasted by a later step of the same job. Artifacts,
  caches, and outputs filled by an action are not followed, and a pairing
  counts as new only if no job had it before.
  `docs/CROSS_JOB.md` lists the cases this misses.
- Secrets and outsider-controlled values are recognised inside `${{ }}` in
  dot and bracket form and in any capitalisation. Not recognised: a `}}`
  inside a quoted string and `github.token` used in place of
  `secrets.GITHUB_TOKEN`.
- An outsider-controlled value inside an expression in a command is reported
  as an injection unless it is only compared (`==`, `!=`, `<`, `>`) or sits
  inside `contains()`, `startsWith()` or `endsWith()`. Other cases where the
  value cannot reach the command are still reported, which errs on the side
  of warning.
- A project that posts with a token other than the built-in one must set
  `PIPEDELTA_COMMENT_AUTHOR` to that account's name, or it will get a new
  comment on every run.
- The image is built from `python:3.12-slim` by tag, not by digest, so the
  tool does not yet meet its own pinning advice for its base image.
- It reads workflow files only. It does not look inside the outside actions a
  workflow calls, or inside scripts that a step runs.
- Network destinations are found only when a full web address is written in
  the command. An address built from variables is missed.
- A pull request that edits or removes the PipeDelta workflow itself can
  switch the check off. The project owner has to mark the check as required
  in the branch settings for it to be a real gate.
- Permissions are worked out per job from the file alone. The repository's
  default, organisation limits and the read-only token given to pull requests
  from forks are not visible, so some changes are reported as "unknown".
- A power dropped from one job but still held by another is reported as a
  reduction for that job, unless another job received it in the same change
  (then it is treated as a move).
- Trigger filters (`branches`, `types`, `paths`) and `if:` conditions are not
  modelled. Widening a filter or deleting a guard condition is not reported.
- Scope names in `permissions:` are compared exactly as written, including
  capital letters.
- The levels (low, medium, high) are rules written by hand. See
  `docs/EVALUATION.md` for how they performed and where they are noisy.
