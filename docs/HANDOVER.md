# PipeDelta: final technical handover

Status: implementation frozen on the `platform` branch for the expo on
**20 November 2026**. Repository: <https://github.com/Vachana7/pipedelta>.
Presenter: Vachanashree S.

## 1. What it is

A tool that reads a change to a GitHub Actions workflow and reports, in plain
sentences, what new powers the pipeline gained (secrets, a token that can
write, outside addresses, outside code, outsider-controlled text in commands),
with the file line as evidence. It runs as a command line, as a GitHub Action
on pull requests, and as a local web app.

## 2. Architecture

```
 workflow files (before / after)
        |
        v
  pipedelta/  (analysis engine, pure Python, no network)
  powers, permissions, jobs, paths, links, stepflows, expressions
        |   facts per job and step
        v
  delta.py  (what the change added or removed, severity)
  evidence.py (line, snippet, confidence, precision)
        |
   +----+-------------------+-----------------------+
   v                        v                       v
  cli.py                 action.yml +            pipedelta/web/
  (diff, git, action,    Dockerfile              server.py  (HTTP, localhost only)
   serve)                (GitHub Action,         service.py (runs engine, shapes results)
                          PR comment)            store.py   (SQLite history)
                                                 github_client.py (read-only GitHub API)
                                                 reports.py (md, html, json, sarif)
                                                 static/    (browser UI)
```

Data flow in the web app: browser, then JSON API on `127.0.0.1`, then the
service runs the engine on two versions of a workflow, then the result is
stored in SQLite and returned. The GitHub token is read only from the server's
environment variables and is never sent to the browser.

## 3. Technology stack

- Python 3.10 or newer (CI tests 3.10 and 3.12). One runtime dependency: PyYAML.
- Web: Python standard library (`http.server`, `sqlite3`, `urllib`), vanilla JavaScript and CSS. No build step, no CDN, no external fonts.
- Reports: Markdown, HTML, JSON, SARIF 2.1.0.
- Quality: pytest (367 tests), Ruff (check and format), Mypy.
- DevOps: GitHub Actions (`ci.yml`, `pipedelta.yml`), Docker, Docker Compose, container image published to GitHub's registry from `main`.

## 4. Major implemented features

- Effective token permissions and capability comparison between two versions.
- Same-job attack paths (outside address, outside code, outsider text, hidden commands, write token) and whether this change made them possible.
- Outsider text followed through job outputs and step outputs.
- Evidence for each finding: file, job, step, exact line, before and after values, confidence (Written in file, Inferred, File is silent), consequence and remediation.
- Web app: Overview, Analyze (GitHub repository, pasted workflow, five built-in examples), result view (Findings, Jobs and steps, Attack paths with diagram, Compare side by side), finding drawer with Previous/Next, `j`/`k`/arrow keys, Show in diff, Copy for a PR comment, History, Repositories.
- GitHub integration, read-only: connect a repository, list workflows, file history, pull requests, analyse a PR.
- Four downloadable reports per analysis.
- GitHub Action that posts and updates one PR comment and fails at a High level.

## 5. Exact startup commands (Windows PowerShell)

First time, with internet:

```powershell
cd $HOME\Documents\pipedelta
git checkout platform
git pull
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Each time:

```powershell
cd $HOME\Documents\pipedelta
.\.venv\Scripts\Activate.ps1
Remove-Item Env:PIPEDELTA_GITHUB_TOKEN, Env:GITHUB_TOKEN, Env:GH_TOKEN -ErrorAction SilentlyContinue
Remove-Item demo.db -ErrorAction SilentlyContinue
pipedelta serve --db demo.db
```

Open <http://127.0.0.1:8765>. Offline command-line fallback (needs Docker, built once beforehand): `docker compose run --rm safe`, `attack`, `fixed`.

## 6. Demo commands and expected outputs

Full script and click table: `docs/DEMO.md`. Summary, using Analyze then Examples:

| Example | Level | Findings | Attack paths | Gate |
|---|---|---|---|---|
| An ordinary change | Low | 1 | 0 | pass |
| A pull request adds a deploy job | High (gauge 5) | 5 | 3, all new | fail |
| The deploy job, fixed | Medium | 1 | 0 | pass |
| Outsider text passed between jobs | High | 1 (outsider text pasted into a command) | 1 | fail |
| Outsider text passed between steps | High | 1 (outsider text pasted into a command) | 1 | fail |

The fixed example is not "Clear": the outside action is now locked to a commit
but is still outside code.

## 7. Test results

Last verified on the `platform` branch, commit `71a8b6a`:

- Local: 367 tests pass; Ruff check and Ruff format clean.
- GitHub Actions on `71a8b6a`: test (3.10) success, test (3.12) success, docker success, review success, publish skipped (publish runs on `main` only); the PipeDelta self-check workflow succeeded.
- Browser check in Chrome at 1280 px and 390 px: tabs, keyboard navigation, copy, Show in diff, attack-path diagrams, all five examples, no console errors, no horizontal scrolling.
- Real GitHub flow (repository connection, PR analysis, four report downloads) was verified earlier with a token held only in the server's environment; the token did not appear in any API response or server log.

Evaluation figures (details in `docs/EVALUATION.md`, `docs/EVIDENCE.md`):

- 8 of 12 attack cases blocked at the default gate (8 of 10 where a workflow file changes). Not independent: rules were adjusted to the first version's misses (6 of 10).
- 159 of 1,659 real past workflow commits (9.6%) would be blocked, down from 23.1%. This measures alert volume, not accuracy; the commits are not labelled.
- Evidence engine over 2,808 real file pairs gave 4,534 findings with no crash, no invalid line number, and 96.8% located to the exact line.

## 8. Known limitations

- Reads workflow files only. It does not look inside the outside actions a workflow calls, and cannot see an attack that changes no workflow file (for example a moved version tag).
- Misses addresses built from variables; outsider text through `env` and artifacts is not followed.
- Rule-based, with hand-written levels. No precision or recall figure exists, because the real-history alerts were never labelled.
- Step-output and job-output rules are tested on constructed cases and have never fired on the real history.
- An attacker can remove the check in the same pull request unless the repository marks it as required.
- Closest existing tool is ci-delta, which also compares base and head workflows. No comparison with ci-delta or zizmor has been run, so no claim is made about which finds more.
- Not tested with real reviewers. Python 3.14 on the demo laptop is untested by CI (3.10 and 3.12 are).
- Localhost only by design; not a multi-user service.

## 9. Important files and their responsibilities

| File | Responsibility |
|---|---|
| `pipedelta/powers.py` | Finds the capabilities a workflow file holds |
| `pipedelta/permissions.py` | Works out the effective token permissions |
| `pipedelta/jobs.py`, `links.py` | Per-job facts and links between jobs |
| `pipedelta/paths.py` | Dangerous pairings inside one job, and which are new |
| `pipedelta/stepflows.py`, `expressions.py` | Outsider text through step and job outputs; `${{ }}` analysis |
| `pipedelta/delta.py` | Compares before and after; severity and levels |
| `pipedelta/evidence.py` | Line numbers, snippets, confidence, precision |
| `pipedelta/report.py`, `github.py` | Text report and GitHub comment/Action helpers |
| `pipedelta/cli.py` | Commands: `diff`, `git`, `action`, `serve` |
| `pipedelta/web/server.py` | HTTP server, routes, Host/Origin/size checks, CSP, localhost only |
| `pipedelta/web/service.py` | Runs the engine and shapes results for the UI (structure, paths, diff rows) |
| `pipedelta/web/store.py` | SQLite history and the Overview statistics |
| `pipedelta/web/github_client.py` | Read-only GitHub API client, allow-listed to `api.github.com`, redirect-restricted |
| `pipedelta/web/reports.py` | Markdown, HTML, JSON and SARIF reports (escaped) |
| `pipedelta/web/samples.py`, `samples/*.yml` | The five built-in examples |
| `pipedelta/web/static/` | `index.html`, `app.js`, `app.css`, `favicon.svg`: the interface |
| `tests/` | 367 tests; `test_web_api.py` covers the API and the security checks |
| `evaluation/` | Attack cases, real-history runner, stored results |
| `.github/workflows/ci.yml` | Tests, Ruff, Mypy, Docker build and smoke test, publish |
| `.github/workflows/pipedelta.yml` | Runs PipeDelta on this repository's own pull requests |
| `Dockerfile`, `docker-compose.yml`, `action.yml` | Container image, offline demo, GitHub Action |
| `docs/` | SETUP, DEMO, PLATFORM, FEATURES_GUIDE, EXPO_PRESENTATION, PROJECT_REPORT, EVALUATION, EVIDENCE |

## 10. Freeze

No further features or architecture changes. Only bug fixes found during
rehearsal, each pushed with approval. `main` is untouched; merging `platform`
and closing other pull requests are the owner's decisions.
