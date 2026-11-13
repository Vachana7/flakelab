# PipeDelta

PipeDelta reviews changes to GitHub Actions workflow files and reports, in plain
language, what new powers a pipeline gained: new secrets it can read, new
permissions, new triggers, new third-party actions, new network destinations.

Status (13 Nov 2026): the core comparison works from the command line.
Not built yet: Docker image, GitHub Action, pull request comment, evaluation.

## Try it

    pip install pyyaml
    python -m pipedelta diff examples/before.yml examples/after-attack.yml
    python -m pipedelta git <base-commit> <head-commit>

The command exits with an error when a change adds a high-level power, so a
pipeline can use it to block the change.

## Known limits

- It reads workflow files only. It does not look inside the outside actions a
  workflow calls, or inside scripts that a step runs.
- Network destinations are found only when a full web address is written in
  the command. An address built from variables is missed.
- The levels (low, medium, high) are rules written by hand, not measured yet.

## History of this repository

This repository previously held a different project, FlakeLab. Its complete
final state is kept on the `flakelab-archive` branch.
