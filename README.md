# FlakeLab

**Experimental root-cause investigation for unreliable CI tests.**
Don't just detect flaky tests. Investigate the conditions behind their failures.

A *flaky test* passes and fails on the same code with nothing changed. Most tools find
flaky tests by re-running them and then guess the cause from failure logs. FlakeLab runs
**controlled experiments** instead: it re-runs your test suite in fresh Docker containers
while changing **one environment condition at a time**, then uses statistics to report
which conditions are associated with each test's failures.

| Condition | How it is applied | What it can reveal |
|---|---|---|
| Baseline | normal resources, network on, default order, UTC | the reference |
| CPU 0.25 core | `docker --cpus 0.25` | timing / deadline assumptions |
| Memory 128 MB | `docker --memory 128m` | memory-hungry tests |
| Network off | `docker --network none` | hidden external dependencies |
| Reverse / shuffled order | pytest plugin reorders tests | shared state between tests |
| Timezone UTC+5:30 | `TZ=IST-5:30` | local-time assumptions |

> **Status:** expo MVP in active development (Nov 2026). See [docs/STATUS.md](docs/STATUS.md).

## Quick start (Docker Desktop)

```bash
git clone https://github.com/<you>/flakelab.git
cd flakelab
docker compose up --build          # FLAKELAB_RUNS=5 docker compose up --build for a quick run
```

Open <http://localhost:8080> and watch the results fill in. The demo project
(`demo/`, a small shop backend) contains deliberately planted flaky tests with known
causes, listed in `demo/flakelab-expected.json`.

## Use it on your own project

Your project needs a Docker image that contains the code, its tests and pytest:

```bash
pip install .                                   # FlakeLab itself has no dependencies
docker build -t my-app:test .
flakelab run --runner docker --image my-app:test --runs 10 --out results
flakelab serve --dir results                    # dashboard on http://localhost:8080
flakelab report --results results/results.json  # Markdown report
```

Without Docker, `--runner local --repo path/to/project` runs the order and timezone
experiments only (CPU, memory and network limits need containers and are skipped, never faked).

## How FlakeLab reaches a conclusion

1. **Interleaved schedule.** Runs alternate between conditions (baseline, CPU, memory, ...,
   baseline, CPU, ...) so slow drift on the machine is spread across all conditions.
2. **Fresh container per run.** No state leaks from one run to the next.
3. **Fisher's exact test** compares each condition's failure count with the baseline.
4. **Holm-Bonferroni correction** controls false alarms from testing several conditions.
5. **Three levels of claim:**
   - *Confirmed observation*: a measured difference, e.g. "failed 10/10 runs with CPU limited
     vs 0/10 at baseline, p < 0.001".
   - *Supported hypothesis*: what that suggests, e.g. "resource sensitivity". An association,
     not proof of the root cause.
   - *Unknown*: the test is unreliable but no tested condition explains it.
6. **Failure clustering** groups tests that fail in the same runs, since related flaky tests
   often share one cause.

## Limitations (read before trusting a result)

- With 10 runs per condition, only large effects can be detected (roughly 6/10 vs 0/10).
  Rare flakiness shows up as "unknown" or "weak signal". More runs give more power.
- A condition being associated with failures does not prove it is the root cause.
- CPU experiments depend on the host; running experiments in parallel (`--workers > 1`)
  makes runs compete for CPU and can blur results.
- Results on the demo project come from planted fixtures and only show the tool works as
  designed; they are not evidence of accuracy on real-world projects.

## Research this builds on

- Silva et al., *The Effects of Computational Resources on Flaky Tests* (FSE 2025):
  46.5% of flaky tests in their dataset were resource-affected.
- Parry et al., *Systemic Flakiness* (EASE 2025): 75% of flaky tests fail in clusters that
  share root causes.
- Shaker (resource stress for flaky-test detection) and iDFlakies (order-dependent tests)
  are prior tools for parts of this problem; FlakeLab combines controlled experiments with
  statistical diagnosis and reproduction. A full comparison is in progress in `docs/`.

## Development

```bash
pip install -e ".[dev]" ruff mypy
pytest -q && ruff check . && ruff format --check . && mypy flakelab
```

CI (`.github/workflows/`): `ci.yml` runs on every push (quality checks, image builds, a real
Docker integration test, image publishing on `main`); `flakelab-pr.yml` runs a short
experiment on pull requests and comments the report; `flakelab-extended.yml` runs the full
experiment on demand or weekly and publishes the dashboard to GitHub Pages.

## License

MIT
