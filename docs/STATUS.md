# FlakeLab engineering status

Living record of what is done, verified, outstanding and blocked. Updated at the end of
every work session. "Verified" means a command was actually run and its output checked.

## Last update: 2026-11-11

### Verified
| What | How it was verified |
|---|---|
| 26 unit tests pass | `pytest -q` → 26 passed |
| Lint, formatting, types clean | `ruff check .`, `ruff format --check .`, `mypy flakelab` |
| Order-dependency diagnosis | local run, 8 runs/condition: `test_reserve_stock`, `test_low_stock_alert` 8/8 reversed vs 0/8 baseline, p < 0.001 |
| Timezone diagnosis | same run: `test_report_title` 8/8 vs 0/8, p < 0.001 |
| Random test is not blamed on a condition | `test_session_tokens_unique` → "unknown" |
| CPU-sensitive demo test behaves as designed | fails 3/3 when pinned to one core with 3 competing processes, passes 3/3 otherwise |
| Memory-sensitive demo test behaves as designed | fails under a 180 MB memory limit (`ulimit -v`), passes without |
| Dashboard renders | headless Chrome screenshot; only browser error was a missing favicon (fixed) |
| docker-compose file is valid | `docker compose config -q` |
| Workflow files are valid YAML | parsed with PyYAML |

| **Docker runner on real Docker** | GitHub Actions run 43046637552 (ubuntu runner): `test_delivery_forecast` failed 3/3 with `--network none`, `test_export_catalog` 3/3 with `--memory 128m`, `test_authorize_within_sla` 3/3 with `--cpus 0.25`, `test_discount` 0/3 (stable control) |
| FlakeLab image + Docker-out-of-Docker | same run: FlakeLab container drove the host Docker engine through the socket and wrote results |
| CI quality job | ruff, format, mypy, 26 tests on Python 3.10 and 3.12 all green |
| Image publishing to GHCR | run 43047113320 (attempt 2): `flakelab`, `flakelab-demo`, `flakelab-weather-api` pushed to ghcr.io/vachana7. Root cause of the first failure: images had no `org.opencontainers.image.source` label, so GITHUB_TOKEN could not create linked packages. After adding it, the first *creation* of the second package was still denied once and succeeded on re-run; this looks like a delay in GitHub linking a newly created package and should not recur now that the packages exist. Watch for it. |

### Written but NOT yet verified
| What | Why not | Plan |
|---|---|---|
| docker-compose stack end to end | needs a machine with Docker Desktop | Vivek's laptop |
| PR comment, GitHub Pages deploy | needs a PR / Pages enabled | open a test PR; enable Pages (Settings -> Pages -> GitHub Actions) |

### Blockers
- None. Repository live at https://github.com/Vachana7/flakelab

### Notes
- GitHub warns that actions/checkout@v4 and setup-python@v5 target Node 20 (forced onto Node 24). Works today; upgrade the action versions in a later pass.

### Outstanding (in priority order)
1. Real Docker verification (CI + laptop), fix whatever breaks.
2. Pillar C: reproduction capsules (exact order, environment capture, `capsule verify`).
3. Pillar B: Failure DNA (signature clustering, cluster evidence, quality metric).
4. Evaluation harness: rerun-only comparison at equal budget, false-positive and
   inconclusive rates, timing and overhead, clustering quality, charts.
5. Dashboard v2, GitHub Pages.
6. Real open-source repository trial; research comparison matrix.
7. Documentation: architecture, methodology, evaluation report, setup and viva guides.

### Decisions log
| Date | Decision | Reason |
|---|---|---|
| 11 Nov | No React/TypeScript before the expo | no npm in the build sandbox; adds a build step and dependencies with no benefit to the experiment; current dashboard works offline with zero dependencies |
| 11 Nov | No FastAPI yet | FlakeLab is a CLI + static dashboard; an API only if the expo needs visitor-triggered runs (standard library would suffice) |
| 11 Nov | Network isolation only, no latency/loss injection before the expo | needs NET_ADMIN and `tc` inside every project image |
| 11 Nov | No locale condition | Python's UTF-8 locale coercion (PEP 538) makes locale changes in slim images nearly ineffective; documented instead of faked |
| 11 Nov | Standard library only at runtime | installs anywhere, works offline at the expo, nothing to break |
