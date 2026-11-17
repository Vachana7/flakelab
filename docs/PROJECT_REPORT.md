# PipeDelta: project report

## 1. Summary
PipeDelta tells a code reviewer what **new powers** a change gives a GitHub Actions pipeline. It compares the old and the new workflow file and reports each new power with a level, the file, job, step and line, the value before and after, why it matters and what to do. It is available as a GitHub Action (comments on pull requests), a command line, and a local web application.

## 2. The problem
CI/CD pipelines run automatically and often hold powerful credentials, a write-capable token and the ability to run third-party code. A small edit to a workflow file in a pull request can give an attacker those powers: expose a secret to an internet address, run an unpinned third-party action, switch to a dangerous trigger such as `pull_request_target`, raise the token's permissions, or paste text a stranger controls (a pull request title) into a command. Reviewers see a line-by-line YAML diff. It does not say what the change makes possible, and the danger is often in how the change combines with the rest of the file.

## 3. The gap
- Many tools check a workflow *as it is*. A reviewer deciding on a *pull request* needs to know what *changed*.
- Findings in raw YAML terms are hard for non-specialist reviewers. Plain sentences with the line and the fix are easier to act on.
- A new power can be harmless alone and dangerous next to an existing one (for example a new secret in a job that already contacts an outside address). Rating a change by what it sits next to is not what a line diff does.

This describes the gap as I understand it. I have not run a head-to-head comparison with other tools, so I do not claim PipeDelta finds more.

## 4. What was built
1. **Engine** (`pipedelta/`): reads powers, computes effective token permissions, compares versions, rates new powers by what they sit next to in their job, follows outsider-controlled text through job outputs and step outputs, and finds the exact line.
2. **Evidence** (`evidence.py`, `docs/EVIDENCE.md`): severity, confidence (written in file / inferred / file is silent), file, job, step, line, previous and new value, consequence and remediation.
3. **GitHub Action** (`action.yml`): posts and updates one PR comment and can fail the check on High.
4. **Command line:** `pipedelta diff`, `pipedelta git`, `pipedelta serve`.
5. **Web application** (`pipedelta/web/`): GitHub client (read-only), analysis service, SQLite history, four report formats (Markdown, HTML, JSON, SARIF), a localhost-only server, and a no-build interface with overview, analyze, results (findings, evidence drawer, compare, jobs and steps, attack paths), history and repositories.
6. **Tests and CI:** 366 tests; CI runs Ruff, Mypy, tests on Python 3.10 and 3.12, builds and runs a Docker image against example workflows, starts the web app in the container and checks it, and runs PipeDelta on its own pull requests.

## 5. Tools and technologies used
| Area | Tools |
|---|---|
| Language | Python 3.10+ (tested on 3.10 and 3.12) |
| Parsing | PyYAML (only runtime dependency), including source positions for line numbers |
| Web server | Python standard library `http.server`, `sqlite3`, `urllib` |
| Front end | Plain HTML, CSS and JavaScript (no framework, no build step, no CDN) |
| Reports | Markdown, HTML, JSON, SARIF 2.1.0 |
| Quality | pytest, Ruff (lint and format), Mypy |
| CI/CD | GitHub Actions, Docker, Docker Compose, GitHub Container Registry |
| Integration | GitHub REST API (read-only) |
| Source control | Git, GitHub pull requests |
| Dev tooling | VS Code, Chrome; Playwright was used to test the interface during development |

## 6. How it works in one paragraph
For each workflow file it lists the powers: triggers, token permissions (per job, effective), secrets read, outside actions and whether they are pinned, internet addresses, and where outsider-written text is pasted into commands. It does this for the old and new versions and keeps what is new. Each new power gets a level based on its own kind and on what it sits next to in the same job, and outsider text is followed through job and step outputs. The evidence module then finds the line, step and values. Removed powers and safer changes are reported but never raise the level.

## 7. Results (measured, with their limits)
| Measure | Result | What it means |
|---|---|---|
| Attack cases blocked at the default gate | 8 of 12 (8 of 10 where a workflow file changes) | Not independent: the rules were adjusted to the misses of the first version (6 of 10) |
| Real past workflow commits blocked | 159 of 1,659 (9.6%), from 23.1% in the first version | Alert volume, not accuracy; the commits are not labelled |
| Evidence engine over real history | 2,808 file pairs, 4,534 findings, no crash, no bad line number, 96.8% located to the exact line | Checks robustness and location, not whether findings are right |
| Automated tests | 366 pass | |
Details and method: `docs/EVALUATION.md`, `docs/EVIDENCE.md`. The newest rules (outsider text through job and step outputs) are tested on constructed cases and have never fired on the real history, so no improvement in real-world detection is claimed.

## 8. How it compares with existing approaches
This section is from general knowledge of the tool categories and from the project's own testing. **No comparison on shared test cases was run.** Check each tool's current documentation before stating details about it.

| Approach | Typical focus | Relation to PipeDelta |
|---|---|---|
| Workflow linters and static analysers (for example actionlint, zizmor) | Report problems in a workflow file as it is | PipeDelta reports what a *change* added, with plain sentences and evidence. They can be used together |
| Repository security scorecards (for example OpenSSF Scorecard) | Score a whole repository's practices, such as token permissions and pinned dependencies | PipeDelta works per pull request, not per repository score |
| Code scanning with queries (for example CodeQL) | Find vulnerabilities by queries over code | PipeDelta is narrower: workflow powers and their change |
| Dependency update tools (for example Dependabot) | Keep actions and packages up to date | Different job. PipeDelta reviews the change itself |
| Runtime monitoring of runners (for example StepSecurity Harden-Runner) | Watch network and process activity while the pipeline runs | PipeDelta works before the change is accepted, by reading files only |

**Where PipeDelta aims to be different:** change-focused, plain-language, evidence with the line, ranked by combination with what is already in the job, and usable locally with a small, dependency-light code base.
**Where it is weaker, honestly:** it reads workflow files only, has no runtime view, covers fewer rule types than mature scanners, is rule-based with limited tuning data, and has not been tested with real reviewers.

## 9. Limitations
- It reads workflow files only, not the outside actions or scripts they call.
- It judges what a file makes possible, not whether anyone exploited it.
- It misses addresses built from variables and attacks that change no workflow file (such as a moved version tag).
- Outsider text through job-level `env`, artifacts or caches is not followed. Multi-line `name<<EOF` outputs can over-report.
- Inferred findings are plausible, not proven.
- The web app is single-user with no login and local history.
- A pull request can remove the check unless the owner marks it as required.
- Not compared head-to-head with other scanners; no reviewer study.

## 10. Future work
Compare against zizmor on the same cases; label a sample of the blocked commits to measure precision; test the sentences with real reviewers; follow outsider text through `env` and artifacts; add more rule types.

## 11. Repository layout
`pipedelta/` engine; `pipedelta/web/` web app; `tests/` 366 tests; `examples/` sample workflows; `evaluation/` scripts and results; `docs/` documents; `.github/workflows/` the project's CI/CD; `Dockerfile` and `docker-compose.yml`; `action.yml` the GitHub Action.
