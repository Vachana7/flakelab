# Lesson 3: CI/CD and GitHub Actions

**Code for this lesson:** `.github/workflows/*.yml`, `scripts/check_integration.py`

## A. Fundamentals

- **Continuous Integration (CI):** every change is automatically built and tested, so
  breakage is found minutes after it's introduced, not weeks later.
- **Continuous Delivery/Deployment (CD):** every change that passes CI is automatically
  packaged (and optionally deployed). FlakeLab's CD publishes Docker images to the GitHub
  Container Registry (GHCR) on every push to `main`.

**GitHub Actions vocabulary:** a *workflow* (YAML file) is started by *events* (`push`,
`pull_request`, `workflow_dispatch`, `schedule`). It contains *jobs* that run on *runners*
(fresh virtual machines). Jobs contain *steps*: shell commands or reusable *actions*
(`actions/checkout@v4`).

## B. Theory

- **Jobs run in parallel unless `needs:` creates a dependency.** Our pipeline is a small
  DAG: `quality → docker → publish`.
- **Matrix builds** run one job per combination: we test Python 3.10 and 3.12.
- **`GITHUB_TOKEN`** is a short-lived token created for each workflow run. `permissions:`
  restricts what it can do (least privilege): read-only by default, `packages: write` only
  in the publish job.
- **Concurrency groups** cancel outdated runs of the same branch, saving minutes.
- **Artifacts** keep files produced by a job (results, dashboards) after the runner is deleted.

## C. In our code

| Workflow | Trigger | What it proves |
|---|---|---|
| `ci.yml` | every push/PR | code quality, image builds, that Docker conditions are really applied (`check_integration.py`), capsule replay and verification, images published |
| `flakelab-pr.yml` | PRs touching code/tests | short experiment, report as a PR comment |
| `flakelab-extended.yml` | manual, weekly, tags | full experiment, dashboard to GitHub Pages |
| `evaluation.yml` | manual | the research evaluation on FlakeBench |

## D. Design decisions

- **Integration test checks raw counts, not verdicts:** with 3 runs nothing can be
  significant, and the question there is only "were the limits applied?".
- **Capsule verification uses 6 runs per arm:** 4 runs gave p = 0.07 for a real 4/4 vs 1/4
  result, which is insufficient power, not a bug.
- **Long experiments are manual or scheduled** so CI time and cost stay bounded.

## E. Alternatives

Jenkins (self-hosted, flexible, more maintenance), GitLab CI (similar YAML model), CircleCI.
GitHub Actions was chosen because the code already lives on GitHub and public repositories
get free minutes.

## F. Cost and speed

The quality job takes about 25 s; the Docker job about 2–3 minutes. PR experiments are
capped by path filters, 5 runs per condition and timeouts.

## G. Security

- Never use `pull_request_target` with code checkout from forks: it runs untrusted code with
  write permissions. That pattern was used in real 2025–2026 supply-chain attacks.
- Pin third-party actions (ideally to a commit SHA) and give each job only the permissions it needs.
- Never put secrets in workflow files; use repository secrets.

## H. Interview questions

1. What's the difference between continuous delivery and continuous deployment?
2. How would you make a slow CI pipeline faster without losing safety?
3. Why is `pull_request_target` dangerous?
4. What does `needs:` do, and what happens to `publish` if `docker` fails?
5. A workflow is flaky. How would FlakeLab's ideas help you debug it?

## I. Exercises

1. Open the latest CI run in the Actions tab. Find the step that runs `check_integration.py`
   and read its PASS lines. Which Docker flag does each line prove?
2. Create a branch, change `demo/shop/pricing.py` so `test_discount` fails, open a pull
   request, and watch CI and the FlakeLab PR comment. Then close the PR without merging.
3. Why does `publish` have `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`?
