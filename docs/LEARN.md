# What you need to understand to explain PipeDelta

Read one part per day. Each part ends with questions. Answer them in your own
words in the chat and they will be checked.

## Part 1: what a pipeline is

A **pipeline** is a list of instructions that GitHub runs automatically when
something happens in a repository, for example when someone pushes code. The
instructions live in files under `.github/workflows/`. Each file is called a
**workflow** and is written in a format called YAML.

Open `examples/before.yml`. Its parts:

- `on:` says **when** it runs. Here: on every push and every pull request.
- `permissions:` says what the pipeline's own key (called a **token**) may do
  to the repository. `contents: read` means it can read the code but not change it.
- `jobs:` holds the work. Each job runs on a fresh computer that GitHub lends you.
- `steps:` are the instructions inside a job, done in order.
- `uses:` runs a ready-made program written by someone else, called an **action**.
- `run:` runs a command you wrote yourself.

A **secret** is a password stored in the repository settings, such as the key
to a cloud account. A workflow reads it with `${{ secrets.NAME }}`.

Why attackers care: a pipeline runs automatically, can hold the keys to
publish software, and few people read changes to it carefully.

Questions:
1. In `examples/before.yml`, when does the pipeline run, and what is it allowed to do to the repository?
2. What is the difference between `uses:` and `run:`?
3. Why is a secret more dangerous in a job that also contacts an internet address?

## Part 2: how PipeDelta works

Three steps, one file each:

1. `pipedelta/powers.py` reads one workflow file and writes down every
   **power** it has: each trigger, permission, secret, outside action and
   internet address.
2. `pipedelta/delta.py` does that for the old file and the new file, and keeps
   only the powers that are new. Then it gives each one a level and a sentence.
3. `pipedelta/report.py` turns the result into text or a pull request comment.

Two rules worth knowing by heart:

- An outside action written as `name@v1` is **high**, because the author can
  later change what `v1` means. Written as `name@` followed by 40 letters and
  digits (a commit id) it is **medium**, because that exact code can never change.
- A new internet address is **medium** alone, but **high** when the same job
  can also read a secret.

Questions:
1. Why does PipeDelta report only gained powers and not everything in the file?
2. Why is `@v1` riskier than a 40-character commit id?
3. Open `tests/test_delta.py`. Pick one test and say in one sentence what it proves.

## Part 3: Docker and the pipeline of this project

A **Docker image** is a sealed box holding a program and everything it needs
to run. A **container** is that box running. The `Dockerfile` is the recipe:
start from a small Python box, add git, copy PipeDelta in, install it.

Why Docker here: GitHub can run the tool the same way on any repository
without the user installing Python or anything else.

This repository has two workflows of its own:

- `ci.yml`: test the code, build the image, check the image against the
  examples, publish the image.
- `pipedelta.yml`: run PipeDelta on this repository's own pull requests.

Notice that both follow the advice PipeDelta gives: read-only permissions by
default, and outside actions locked to commit ids.

Questions:
1. What is the difference between an image and a container?
2. In `ci.yml`, why does the `docker` job have `needs: test`?
3. `pipedelta.yml` uses `pull_request` and not `pull_request_target`. Why does that matter?
