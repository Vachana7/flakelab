# FlakeLab architecture

## Components

```mermaid
flowchart LR
    subgraph CLI["flakelab CLI (cli.py)"]
      RUN[run] --- CAP[capsule create / verify] --- BEN[benchmark] --- SRV[serve / report]
    end
    RUN --> EXP["Experiment (experiment.py)<br/>interleaved schedule, live results.json"]
    EXP --> RUNNERS{"Runner (runners.py)"}
    RUNNERS -->|fresh container per run| DOCKER["DockerRunner<br/>--cpus --memory --network, TZ, order"]
    RUNNERS -->|subprocess| LOCAL["LocalRunner<br/>order, TZ only"]
    DOCKER --> PLUGIN["pytest plugin (plugin/)<br/>reorders, records outcomes after every test"]
    LOCAL --> PLUGIN
    EXP --> AN["analyze() (analyzer.py)"]
    AN --> STATS["stats.py<br/>Fisher exact, Holm-Bonferroni"]
    AN --> CL["clustering.py<br/>co-failure (Jaccard)"]
    AN --> DNA["dna.py<br/>Failure DNA (Chebyshev), ARI"]
    EXP --> OUT[("results.json<br/>report.md<br/>capsules/")]
    OUT --> DASH["dashboard/index.html<br/>polls results.json"]
    CAP --> CAPS["capsule.py<br/>order + environment + scripts"]
    BEN --> BM["benchmark.py + charts.py<br/>FlakeLab vs reruns, equal budget"]
```

## One experiment run, step by step

```mermaid
sequenceDiagram
    participant E as Experiment
    participant R as DockerRunner
    participant D as Docker engine
    participant C as Test container
    E->>R: environment()
    R->>D: image inspect, run env probe, docker info
    loop for each (condition, run) in interleaved schedule
      E->>R: run(condition, i)
      R->>D: docker create (limits, env, network)
      R->>D: docker cp plugin (+ order file) into container
      R->>D: docker start -a
      D->>C: python -m pytest -p flakelab_pytest_plugin
      C-->>C: plugin writes outcomes JSON after every test
      R->>D: docker inspect (OOMKilled), docker cp results out, docker rm
      R-->>E: RunResult(outcomes, order, timings)
      E->>E: analyze() and atomically rewrite results.json
    end
    E->>E: capsules for every investigated failure
```

## CI/CD pipeline

```mermaid
flowchart LR
    PUSH[push / PR] --> Q["quality<br/>ruff, format, mypy,<br/>pytest on 3.10 + 3.12"]
    Q --> DK["docker<br/>build images, smoke tests,<br/>real-Docker integration,<br/>capsule create + verify,<br/>Docker-out-of-Docker"]
    DK -->|main only| PUB["publish<br/>images to GHCR"]
    PR[pull request] --> FPR["flakelab-pr<br/>5 runs/condition,<br/>PR comment + artifact"]
    MAN[manual / weekly / tag] --> EXT["flakelab-extended<br/>15 runs/condition,<br/>GitHub Pages dashboard"]
    MAN2[manual] --> EV["evaluation<br/>FlakeBench, FlakeLab vs reruns"]
```

## Modules

| Module | Responsibility | Key ideas |
|---|---|---|
| `conditions.py` | What each experiment changes | one variable per condition; baseline pins TZ and order |
| `runners.py` | Execute the suite once | fresh container per run, plugin injected with `docker cp`, OOM detection, environment capture |
| `plugin/flakelab_pytest_plugin.py` | Inside the project's pytest | reverse / seeded shuffle / explicit replay; atomic write after every test (crash attribution) |
| `experiment.py` | Orchestration | interleaved schedule, thread pool (default 1 worker), live results, timing, capsules |
| `stats.py` | Statistics | one-sided Fisher exact test from the hypergeometric distribution; Holm-Bonferroni |
| `analyzer.py` | Verdicts | confirmed observation / supported hypothesis / unknown; evaluation against ground truth |
| `clustering.py` | Generic clustering | average-linkage agglomerative with cached distances; Jaccard co-failure groups |
| `dna.py` | Failure DNA | per-condition failure-rate signatures, Chebyshev distance, cluster evidence, ARI |
| `capsule.py` | Reproduction capsules | failing-order prefix, environment, scripts, statistical `verify` |
| `benchmark.py`, `charts.py` | Evaluation | equal-budget comparison with reruns, SVG charts, EVALUATION.md |
| `report.py` | Markdown | PR comments and CI job summaries |
| `cli.py` | Entry point | input validation, subcommands |

## Data model (`results.json`)

```
meta        tool, version, runner, target, status, runs_per_condition, alpha, seed,
            conditions[{name,label,category,description,docker_args,env}],
            environment{image, project{python, os, packages}, host, revision},
            timing{wall, mean_run, mean_pytest, mean_overhead, flakelab_cpu, max_rss},
            capsules[{test, path}]
tests[]     nodeid, per_condition{cond: {runs, failures, rate}}, observations[],
            verdict{level, categories, title, explanation, fix}, reproduce,
            hidden_sensitivity, dna[rates], dna_cluster, cluster
dna         conditions, threshold, clusters[{signature, spread, common_conditions,
            evidence, co_failure_similarity, confidence, limitations}], quality{ARI}
clusters[]  co-failure groups
summary     counts
evaluation  (with --expected) accuracy, false positives, inconclusive rate, ...
runs[]      every run: condition, index, outcomes, order, order_env, durations, notes
```

## Design decisions

| Decision | Why | Alternative rejected |
|---|---|---|
| Fresh container per run | no state leaks between runs; each run is an independent sample | reuse one container: faster, but leaked state breaks independence |
| Inject plugin with `docker cp` | works with any project image, no rebuild | require users to add the plugin to their image |
| Write outcomes after every test, atomically | an OOM kill mid-run still tells us which test was running | write once at the end: a crash loses the whole run |
| Interleave conditions | slow drift (heat, background load) spreads over all conditions | blocks per condition: drift would look like an effect |
| One worker by default | parallel runs compete for CPU and blur CPU experiments | parallel by default: faster but confounded |
| Standard library only | installs anywhere, works offline at the expo | scipy / FastAPI / React: more dependencies, no gain for the experiment |
| Static dashboard polling JSON | zero server logic, works from GitHub Pages and offline | web app with an API |
| Docker-out-of-Docker via socket | FlakeLab's container controls sibling containers | Docker-in-Docker: privileged, slower, nested storage |
