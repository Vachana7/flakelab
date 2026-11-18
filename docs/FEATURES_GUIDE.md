# PipeDelta feature guide: every screen, and how it connects to DevOps

Read this to understand each part of the web app well enough to explain it to
experts. Each feature has: what it does, how to use it, what the engine does
behind it, and the DevOps idea it belongs to.

## 0. The DevOps background in six sentences

- **CI/CD** (continuous integration and delivery) means code changes are tested, built and released by automated **pipelines**.
- On GitHub, a pipeline is a **workflow**: a YAML file in `.github/workflows/` that says *when* to run (`on:`), *what it may do* (`permissions:`) and *what to do* (`jobs:` made of `steps:`).
- A pipeline is powerful. It can hold **secrets** (deploy keys, tokens), call the internet, run other people's code (**actions**), and change the repository through its **token**.
- Because it runs automatically and few people read changes to it carefully, a small edit to a workflow can give an attacker those powers. This is called **CI/CD supply-chain risk**.
- A **pull request (PR)** is a proposed change that others review before it is accepted. This is where a risky pipeline change should be caught.
- PipeDelta compares the old and new workflow and tells the reviewer, in plain words, **what new powers the change gives the pipeline**.

## 1. Words you will use

| Term | Meaning |
|---|---|
| Power | Something a pipeline can do: a trigger, a token permission, a secret, an outside action, an internet address, running outsider text |
| Finding | One new power found in a change, with level, evidence and advice |
| Level | High, Medium or Low. Chosen by the rules in `pipedelta/delta.py`. High means a harmful combination became possible |
| Gate | The default rule of the GitHub Action: fail the check when a change is High |
| Unpinned action | `uses: owner/name@v1` points to a tag the author can move. Pinning means using the full commit ID |
| Outsider text | Text a stranger controls, such as a pull request title, branch name or comment |
| Script injection | Pasting outsider text straight into a command (`run: echo ${{ github.event.pull_request.title }}`), so the text can run as code |
| `pull_request_target` | A trigger that runs with secrets and a write token even for strangers' pull requests. Dangerous if combined with checking out their code |
| Confidence | *Written in file* (the file says it), *Inferred* (worked out by following where text flows), *File is silent* (unknown) |

## 2. The screens

### 2.1 Overview (home)
**What it shows.** Four counters (analyses run, repositories connected, high-risk changes, findings with evidence), a chart of findings per analysis over time, bars by severity and by confidence, the kinds of power that appeared, and recent analyses.
**Where the numbers come from.** Only from analyses you ran. They are `SELECT` queries over the local SQLite history (`pipedelta/web/store.py`). Nothing is typed in. With no history it shows an empty state.
**DevOps link.** Observability and metrics: a team lead sees how risky the pipeline changes are over time.

### 2.2 Analyze
Three tabs.

**GitHub repository** (the real use).
1. *Connect:* type `owner/name` or a GitHub address. The server asks the GitHub API for the repository and lists `.github/workflows/*.yml`. It is remembered under Repositories.
2. *Choose what to analyze:*
   - **Latest change:** the chosen file's newest commit compared with the commit before it.
   - **Current file:** what the file can do today (no comparison).
   - **Pull request:** every workflow file the PR changes, old version from the base commit, new version from the PR head. This is the real PipeDelta use case.
3. *Run analysis:* the server fetches the files, runs the engine, stores the result, and opens the result page.
**DevOps link.** Pull-request review, version control history, GitHub REST API integration.

**Paste a workflow.** Paste a before and an after (before may be empty) and analyze, with no GitHub needed. Good for trying a change before committing it (shift left).

**Examples.** Five built-in workflow pairs that run with no internet:
1. *A pull request adds a deploy job:* secret + outside address + unpinned action + risky trigger. High.
2. *An ordinary change:* a new test step and a newer GitHub action. Low or none.
3. *The deploy job, fixed:* pinning the action to a commit.
4. *Outsider text passed between jobs:* the edited job looks harmless; another job pastes its output into a command.
5. *Outsider text passed between steps:* one step now writes the PR title to an output; a later step pastes it into a command.

### 2.3 Result page
**Header.** Overall level, how many findings, whether the GitHub Action's default gate would fail, the commits compared, the PR number and author, and Download and Delete buttons.

**Findings tab.** A list, filterable by High, Medium, Low, or Removed/safer. Each row shows the title, the kind, the exact place (file, job, step, line), a one-sentence explanation, and the confidence tag. Powers that were *removed* or *made safer* are listed in green and never raise the level.

**Evidence drawer** (click a finding). This is the most important feature for experts:
- *Where:* file, job, step and line, and how precise it is (exact line, job only, whole file).
- *What changed:* previous value and new value (for example token permission `read` to `write`).
- *Evidence in the file:* the lines around it, with the guilty line highlighted.
- *Why it matters:* the consequence in plain words.
- *What to do:* the fix (for example "pin the action to its full commit ID").
How lines are found is in `docs/EVIDENCE.md` (PyYAML source marks).

**Compare tab.** Old file left, new file right. Changed lines are coloured; a red dot marks any line that has a finding; clicking it opens the evidence. Long unchanged stretches are folded.

**Jobs and steps tab.** For each job: runner, token access ("can write contents"), secrets it reads, outside addresses it contacts, unpinned actions, whether it uses outsider-written text; then its steps in order, with flagged steps highlighted and a button to open their findings.
**DevOps link.** This is the pipeline structure: jobs run on runners, steps run in order, jobs pass data through outputs.

**Attack paths tab.** Dangerous pairings *inside one job* (for example a secret next to an outside address), and whether *this change* made them possible or they already existed.

**Download report.** Markdown (paste in a ticket), HTML (one file, prints well), JSON (the full result), SARIF 2.1.0 (the standard format GitHub code scanning and many tools read).
**DevOps link.** DevSecOps reporting and integration with other security tooling.

### 2.4 History
Every analysis, newest first, with a filter box. Open one to see the same evidence again. Stored in `pipedelta.db` on your computer (no cloud, no login). Delete removes one.

### 2.5 Repositories
Connected repositories with last analysis level. Analyze, open the last result, or remove.

### 2.6 Side bar
Shows whether a GitHub token is set, the GitHub user and the requests left in the hour. The token itself is never shown.

## 3. How the engine works (for deeper questions)

| Module | Job |
|---|---|
| `powers.py` | Reads one workflow and lists its powers |
| `permissions.py` | Works out each job's *effective* token permissions (workflow level plus job level) |
| `delta.py` | Compares old and new, keeps what is new, gives each a level and sentence |
| `jobs.py`, `paths.py` | Collect facts per job; rate a new power by what it sits next to in its job |
| `links.py` | Follows outsider text through *job outputs* into another job's command |
| `stepflows.py` | Same, between *steps* of one job |
| `expressions.py` | Reads `${{ ... }}` expressions safely (linear time, no recursion limit) |
| `evidence.py` | Finds the line, step and values for each finding |
| `report.py`, `github.py`, `cli.py` | PR comment, GitHub Action wiring, command line |
| `web/` | The web app: GitHub client, service, store, reports, server, interface |

Key idea: it does not ask "is this file bad?" It asks "what can this pipeline do now that it could not do before?"

## 4. The three ways to use it (all the same engine)

1. **GitHub Action** (`action.yml`, `.github/workflows/pipedelta.yml`): comments on the PR and fails the check when a change is High. The comment updates in place.
2. **Command line:** `pipedelta diff old.yml new.yml` (exit code 1 means High), `pipedelta git <base> <head>`.
3. **Web app:** `pipedelta serve`.

## 5. The project's own CI/CD (course topics)

| Stage | What happens | Course topic |
|---|---|---|
| Test | Ruff lint, format check, Mypy, 366 tests on Python 3.10 and 3.12 | Continuous integration |
| Build | Docker image built and run against safe, attack, fixed and output/step examples; the web app is started in the container and checked | Docker, testing containers |
| Publish | Image pushed to GitHub's container registry on `main` | Registry, delivery |
| Review | PipeDelta runs on this repository's own pull requests | Pipelines as code, PR review |
| Offline demo | `docker compose` runs the examples with no network | Docker Compose |

## 6. Security design of the web app (an expert may ask)

- Listens on 127.0.0.1 only; rejects other `Host` headers (DNS-rebinding) and cross-site `Origin`.
- Writes must be JSON; request size capped; strict Content-Security-Policy.
- The GitHub token comes from the server's environment, is never stored, logged or sent to the browser, and the GitHub client refuses redirects away from `api.github.com`.
- The front end builds the page with `textContent` only, so text from a workflow cannot become markup.
- Read-only token: Contents and Pull requests read-only.
- No login: it is for one person on one computer.

## 7. Practice questions

1. What is the difference between a *finding* and a *level*?
2. Why does removing a secret never raise the level?
3. What does *Inferred* mean, and why is it labelled differently from *Written in file*?
4. Why can a workflow be dangerous even if the changed line looks harmless? (Hint: example 4 and 5.)
5. What would a reviewer do differently with this report than with the raw YAML diff?
