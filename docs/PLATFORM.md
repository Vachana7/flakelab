# The PipeDelta web app

A local web app on top of the same engine the GitHub Action uses. It does not
re-implement any rule: it calls `compare()`, `explain()` (docs/EVIDENCE.md),
`job_facts()` and `paths_in()` and shows what they return.

## Start it

    pip install -e .
    export GITHUB_TOKEN=...        # optional; without it only public repositories, 60 requests/hour
    pipedelta serve                # http://127.0.0.1:8765, history in ./pipedelta.db

Options: `--port`, `--host` (stays on 127.0.0.1 unless you change it), `--db`.
A fine-grained, read-only token (Contents and Pull requests: read) is enough.
The token is read once from the server's environment. It is never stored, never
sent to the browser and never appears in an API response.

## Architecture

    browser (vanilla JS/CSS)  ──JSON──▶  server.py  ──▶  service.py ──▶  engine (delta, evidence, jobs, paths)
                                            │                 │
                                            │                 └──▶ github_client.py ──▶ api.github.com (read only)
                                            ├──▶ store.py (SQLite: repos, analyses)
                                            └──▶ reports.py (Markdown, HTML, JSON, SARIF)

| Part | Job |
|---|---|
| `web/github_client.py` | Read-only GitHub calls. Host fixed to `api.github.com`; owner, repo, path and ref are validated before a request is built; rate limit tracked; errors translated to short codes. |
| `web/service.py` | Fetches the right files (latest change of one file, a pull request, current file, pasted text), runs the engine, shapes the result. |
| `web/store.py` | SQLite history. The dashboard statistics are `SELECT`s over stored analyses. Nothing is seeded or typed in. |
| `web/reports.py` | Report formats. All workflow text is escaped. SARIF 2.1.0 can be uploaded to GitHub code scanning. |
| `web/server.py` | JSON API and static files, standard library only. |
| `web/static/` | The interface. No build step, no CDN, works offline. |
| `web/samples/` | The repo's example workflows, so the app can be tried without internet. |

## API

| Request | Returns |
|---|---|
| `GET /api/session` | version, whether a token is set, the GitHub user, remaining rate limit |
| `POST /api/repos {repo}` | repository info and its workflow files; remembers the repository |
| `GET /api/repos`, `DELETE /api/repos/{owner}/{name}` | connected repositories |
| `GET /api/repos/{owner}/{name}/workflows\|history\|pulls` | workflow files, a file's commits, open pull requests |
| `POST /api/analyses {mode: compare\|inventory\|pull\|paste\|sample, ...}` | a full analysis |
| `GET /api/analyses`, `GET/DELETE /api/analyses/{id}` | history, one analysis |
| `GET /api/analyses/{id}/report?format=md\|html\|json\|sarif` | a download |
| `GET /api/stats` | dashboard numbers computed from stored analyses |

Errors are always `{"error": {"code", "message"}}` with a matching HTTP status.

## Security choices (each is tested in `tests/test_web_api.py`)

- Binds to 127.0.0.1. The `Host` header must be a local name (stops DNS rebinding).
- Writes need `Content-Type: application/json` and, if an `Origin` is sent, the page's own origin (stops other websites posting to it).
- Request bodies over 600 KB are refused; GitHub files over 256 KB are refused.
- Strict Content-Security-Policy; the front end builds DOM with `textContent` only, so text from a workflow file can never become markup.
- Static files are served only from the `static` folder.

## What the pages show

- **Overview**: counts, severity and confidence bars, findings over time, kinds of power, recent runs. All from the history.
- **Analyze**: connect a repository, pick a workflow file and *Latest change*, *Current file* or a *pull request*; or paste a workflow (before/after), or load an example.
- **Result**: overall level and gate outcome; findings with the evidence drawer (file, job, step, line, before and after values, the lines themselves, consequence, remediation, confidence); jobs and steps with the facts the engine found; attack paths; side-by-side diff with finding markers; report downloads.
- **History** and **Repositories**: reopen, filter, delete.

## Expo walk-through (about 4 minutes)

1. `pipedelta serve`, open the page. Overview is empty: "No analyses yet". Say that nothing on the page is typed in.
2. Analyze → GitHub repository → `Vachana7/pipedelta` → Connect → *Pull request* → choose #12 or #11 → Run. Show the level, then open a finding: the line, the before and after values, the advice.
3. Same screen, *Compare*: the side-by-side diff, dots on lines with findings.
4. *Jobs and steps*: which job holds which secret and token, which step is flagged.
5. Analyze → Examples → "Outsider text passed between steps": the case where the edited line looks harmless.
6. Download the SARIF or Markdown report. Open History and Overview: the numbers moved.
7. If the network fails, step 5 and the pasted-workflow mode still work.

## Known limits

- It reads workflow files only. It does not look inside the outside actions or scripts a workflow calls.
- Findings judge what the file makes possible, not whether anyone exploited it.
- "Inferred" findings come from following outsider text through job and step outputs. These rules are tested but have never fired on the real history, so treat them as plausible, not proven. Multi-line `name<<EOF` outputs can over-report.
- Outsider text that reaches a command through job-level `env`, artifacts or caches is not followed.
- History is a local SQLite file for one user. There are no accounts and no login; it is not meant to be exposed to a network.
- Private repositories need a token with read access. Rate limit is 60 requests per hour without one.
- The history evaluation numbers in docs/EVALUATION.md measure alert volume, not accuracy. The web app does not change them.
- Real-history check of the evidence engine: 2,808 file pairs from 1,659 commits gave 4,534 findings; no crash, no line number outside the file or off its target, 96.8% located to the exact line, 3.2% to the job, one to the file.
