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
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0
          - uses: Vachana7/flakelab@main
            with:
              token: ${{ github.token }}

## Try it

    pip install pyyaml
    python -m pipedelta diff examples/before.yml examples/after-attack.yml
    python -m pipedelta git <base-commit> <head-commit>

The command exits with an error when a change adds a high-level power, so a
pipeline can use it to block the change.

## Documents

- `docs/DEMO.md`: expo demo script and likely examiner questions
- `docs/EVALUATION.md`: what was measured and what was not
- `docs/UX.md`: personas, user journey, wireframes
- `docs/LEARN.md`: study notes with questions

## Known limits

- It reads workflow files only. It does not look inside the outside actions a
  workflow calls, or inside scripts that a step runs.
- Network destinations are found only when a full web address is written in
  the command. An address built from variables is missed.
- A pull request that edits or removes the PipeDelta workflow itself can
  switch the check off. The project owner has to mark the check as required
  in the branch settings for it to be a real gate.
- The levels (low, medium, high) are rules written by hand. See
  `docs/EVALUATION.md` for how they performed and where they are noisy.

## History of this repository

This repository previously held a different project, FlakeLab. Its complete
final state is kept on the `flakelab-archive` branch.
