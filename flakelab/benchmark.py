"""Evaluation harness: FlakeLab vs plain reruns at the same run budget.

Research question: can controlled environmental experiments identify conditions
associated with flaky tests more effectively than ordinary reruns alone?

Design
* Arm A (FlakeLab): R runs under each of C conditions  ->  R x C runs.
* Arm B (reruns):   R x C runs, all at baseline.        ->  same budget.
Both arms use the same image, machine and seed, and run one after the other.

Metrics (all computed from the two result files, nothing estimated by hand)
1. Detection: share of known problem tests each arm flags as unreliable.
   Reruns flag a test if it both passed and failed. FlakeLab flags it if its
   verdict is supported hypothesis, unknown or weak signal.
2. Diagnosis accuracy (FlakeLab only; reruns produce no attribution).
3. Reproduction rate: failure rate under the condition FlakeLab identified vs
   the failure rate in plain reruns, and the expected runs to see one failure.
4. False-positive rate on known-stable tests, for both arms.
5. Inconclusive and wrong-attribution rates on environment-caused tests.
6. Time: wall clock per arm, per-run overhead outside pytest.
7. FlakeLab's own CPU and memory use.
8. Clustering quality: Adjusted Rand Index of DNA clusters vs planted causes.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from flakelab.charts import PALETTE, grouped_bars
from flakelab.conditions import BASELINE, get_conditions
from flakelab.experiment import Experiment


def run_benchmark(
    runner, runs: int, expected: dict, out_dir: str | Path, conditions=None, log=print
) -> dict:
    out = Path(out_dir)
    conds = conditions or get_conditions(None)
    active = [c for c in conds if runner.supports(c)]
    budget = runs * len(active)
    log(f"Arm A (FlakeLab): {runs} runs x {len(active)} conditions = {budget} runs")
    arm_a = Experiment(
        runner,
        conds,
        runs=runs,
        out_dir=out / "flakelab",
        expected=expected,
        log=log,
        capsules=True,
        project="FlakeBench: FlakeLab arm",
    ).run()
    log(f"Arm B (reruns): {budget} baseline runs")
    arm_b = Experiment(
        runner,
        [BASELINE],
        runs=budget,
        out_dir=out / "reruns",
        expected=expected,
        log=log,
        capsules=False,
        project="FlakeBench: rerun arm",
    ).run()
    metrics = compute_metrics(arm_a, arm_b, expected, runs, budget)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    write_report(metrics, out)
    return metrics


def _flagged_by_reruns(test: dict) -> bool:
    base = test["per_condition"]["baseline"]
    return 0 < base["failures"] < base["runs"]


def _flagged_by_flakelab(test: dict) -> bool:
    return test["verdict"]["level"] in ("supported_hypothesis", "unknown", "weak_signal")


def compute_metrics(arm_a: dict, arm_b: dict, expected: dict, runs: int, budget: int) -> dict:
    tests_a = {t["nodeid"]: t for t in arm_a["tests"]}
    tests_b = {t["nodeid"]: t for t in arm_b["tests"]}
    rows = []
    for nodeid, exp in expected.items():
        a, b = tests_a.get(nodeid), tests_b.get(nodeid)
        if a is None or b is None:
            continue
        b_base = b["per_condition"]["baseline"]
        rerun_rate = b_base["failures"] / b_base["runs"] if b_base["runs"] else 0.0
        rep = a.get("reproduce") or {}
        rows.append(
            {
                "test": nodeid,
                "expected": exp,
                "kind": "stable"
                if exp == "stable"
                else ("intrinsic" if exp == "intrinsic" else "environmental"),
                "rerun_failure_rate": rerun_rate,
                "rerun_flagged": _flagged_by_reruns(b),
                "flakelab_flagged": _flagged_by_flakelab(a),
                "flakelab_level": a["verdict"]["level"],
                "flakelab_categories": a["verdict"]["categories"],
                "flakelab_condition": rep.get("condition"),
                "flakelab_condition_rate": rep.get("failure_rate"),
            }
        )

    def share(xs, pred):
        xs = list(xs)
        return (sum(1 for x in xs if pred(x)) / len(xs)) if xs else None

    problems = [r for r in rows if r["kind"] != "stable"]
    env = [r for r in rows if r["kind"] == "environmental"]
    stable = [r for r in rows if r["kind"] == "stable"]
    ev = arm_a.get("evaluation") or {}
    repro = [
        {
            "test": r["test"].split("::")[-1],
            "rerun_rate": r["rerun_failure_rate"],
            "condition_rate": r["flakelab_condition_rate"],
            "condition": r["flakelab_condition"],
        }
        for r in env
    ]
    ta, tb = arm_a["meta"]["timing"], arm_b["meta"]["timing"]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category": "Deliberately planted fixtures (FlakeBench). Not public datasets, "
        "not real-world repositories.",
        "runs_per_condition": runs,
        "budget_per_arm": budget,
        "conditions": [c["label"] for c in arm_a["meta"]["conditions"]],
        "environment": {
            "target": arm_a["meta"]["target"],
            "host": (arm_a["meta"].get("environment") or {}).get("host"),
            "project": {
                k: ((arm_a["meta"].get("environment") or {}).get("project") or {}).get(k)
                for k in ("python", "os")
            },
            "harness_platform": platform.platform(),
        },
        "counts": {
            "tests": len(rows),
            "problem_tests": len(problems),
            "environmental": len(env),
            "intrinsic": len(problems) - len(env),
            "stable": len(stable),
        },
        "detection": {
            "flakelab_all_problems": share(problems, lambda r: r["flakelab_flagged"]),
            "reruns_all_problems": share(problems, lambda r: r["rerun_flagged"]),
            "flakelab_environmental": share(env, lambda r: r["flakelab_flagged"]),
            "reruns_environmental": share(env, lambda r: r["rerun_flagged"]),
            "flakelab_intrinsic": share(
                [r for r in problems if r["kind"] == "intrinsic"], lambda r: r["flakelab_flagged"]
            ),
            "reruns_intrinsic": share(
                [r for r in problems if r["kind"] == "intrinsic"], lambda r: r["rerun_flagged"]
            ),
        },
        "diagnosis": {
            "accuracy_all": ev.get("accuracy"),
            "correct": ev.get("correct"),
            "scored": ev.get("scored"),
            "inconclusive_rate": ev.get("inconclusive_rate"),
            "wrong_attributions": ev.get("wrong_attributions"),
            "reruns": "Plain reruns cannot attribute a cause (no variable is changed).",
        },
        "false_positives": {
            "flakelab_rate": share(stable, lambda r: r["flakelab_flagged"]),
            "reruns_rate": share(stable, lambda r: r["rerun_flagged"]),
        },
        "reproduction": repro,
        "timing": {
            "flakelab_wall_seconds": ta.get("wall_seconds"),
            "reruns_wall_seconds": tb.get("wall_seconds"),
            "flakelab_mean_run_seconds": ta.get("mean_run_seconds"),
            "reruns_mean_run_seconds": tb.get("mean_run_seconds"),
            "mean_overhead_seconds": ta.get("mean_overhead_seconds"),
            "mean_pytest_seconds": ta.get("mean_pytest_seconds"),
            "flakelab_process_cpu_seconds": ta.get("flakelab_cpu_seconds"),
            "flakelab_process_max_rss_mb": ta.get("flakelab_max_rss_mb"),
        },
        "clustering": (arm_a.get("dna") or {}).get("quality"),
        "rows": rows,
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _row_md(r: dict) -> str:
    exp = r["expected"] if isinstance(r["expected"], str) else "+".join(r["expected"])
    name = r["test"].split("::")[-1]
    flagged = "yes" if r["rerun_flagged"] else "no"
    level = r["flakelab_level"].replace("_", " ")
    cats = ", ".join(r["flakelab_categories"]) or "-"
    rate = _pct(r["rerun_failure_rate"])
    return f"| `{name}` | {exp} | {rate} | {flagged} | {level} | {cats} |"


def write_report(m: dict, out: Path) -> None:
    det, diag, fp, tim = m["detection"], m["diagnosis"], m["false_positives"], m["timing"]
    (out / "chart-detection.svg").write_text(
        grouped_bars(
            "Known problem tests flagged as unreliable (same run budget)",
            ["All problem tests", "Environment-caused", "Internal randomness"],
            [
                (
                    "FlakeLab",
                    [
                        det["flakelab_all_problems"],
                        det["flakelab_environmental"],
                        det["flakelab_intrinsic"],
                    ],
                    PALETTE["flakelab"],
                ),
                (
                    "Plain reruns",
                    [
                        det["reruns_all_problems"],
                        det["reruns_environmental"],
                        det["reruns_intrinsic"],
                    ],
                    PALETTE["reruns"],
                ),
            ],
            max_value=1.0,
        )
    )
    repro = m["reproduction"]
    (out / "chart-reproduction.svg").write_text(
        grouped_bars(
            "Failure rate: plain reruns vs the condition FlakeLab identified",
            [r["test"] for r in repro],
            [
                (
                    "Under FlakeLab's condition",
                    [r["condition_rate"] for r in repro],
                    PALETTE["flakelab"],
                ),
                ("Plain reruns", [r["rerun_rate"] for r in repro], PALETTE["reruns"]),
            ],
            max_value=1.0,
        )
    )
    rows_md = "\n".join(_row_md(r) for r in m["rows"])
    results_md = "\n".join(
        f"| {label} | {a} | {b} |"
        for label, a, b in [
            (
                "Problem tests flagged (all)",
                _pct(det["flakelab_all_problems"]),
                _pct(det["reruns_all_problems"]),
            ),
            (
                "Environment-caused tests flagged",
                _pct(det["flakelab_environmental"]),
                _pct(det["reruns_environmental"]),
            ),
            (
                "Randomness tests flagged",
                _pct(det["flakelab_intrinsic"]),
                _pct(det["reruns_intrinsic"]),
            ),
            (
                "Cause attributed correctly",
                f"{_pct(diag['accuracy_all'])} ({diag['correct']}/{diag['scored']})",
                "not possible",
            ),
            ("Inconclusive (environment-caused)", _pct(diag["inconclusive_rate"]), "n/a"),
            ("Wrong attributions", str(diag["wrong_attributions"]), "n/a"),
            ("False positives on stable tests", _pct(fp["flakelab_rate"]), _pct(fp["reruns_rate"])),
            ("Wall time", f"{tim['flakelab_wall_seconds']} s", f"{tim['reruns_wall_seconds']} s"),
            (
                "Mean seconds per run",
                str(tim["flakelab_mean_run_seconds"]),
                str(tim["reruns_mean_run_seconds"]),
            ),
        ]
    )
    clustering = m.get("clustering") or {}
    ari = clustering.get("adjusted_rand_index")
    report = f"""# FlakeLab evaluation: FlakeBench

> **Result category:** {m["category"]}
> Generated {m["generated_at"]} on {m["environment"]["target"]}.
> Host: {m["environment"]["host"]}. Project Python {m["environment"]["project"]["python"]}.

**Research question.** Can controlled environmental experiments identify conditions
associated with flaky tests more effectively than ordinary reruns alone?

**Design.** Arm A ran FlakeLab: {m["runs_per_condition"]} runs under each of
{len(m["conditions"])} conditions ({m["budget_per_arm"]} runs). Arm B ran plain reruns:
{m["budget_per_arm"]} runs at baseline. Same image, machine and budget.
FlakeBench has {m["counts"]["tests"]} tests: {m["counts"]["environmental"]} with a planted
environmental cause, {m["counts"]["intrinsic"]} with internal randomness and
{m["counts"]["stable"]} stable controls.

## Results

| Metric | FlakeLab | Plain reruns |
|---|---|---|
{results_md}

![Detection](chart-detection.svg)

![Reproduction](chart-reproduction.svg)

**Overhead.** A run took {tim["flakelab_mean_run_seconds"]} s on average, of which
{tim["mean_pytest_seconds"]} s was inside pytest; the rest
({tim["mean_overhead_seconds"]} s) is container create/start/copy/remove. FlakeLab's own
process used {tim["flakelab_process_cpu_seconds"]} s of CPU and at most
{tim["flakelab_process_max_rss_mb"]} MB of memory for the whole FlakeLab arm.

**Clustering quality.** Adjusted Rand Index of DNA clusters vs planted causes:
{"n/a" if ari is None else f"{ari:.2f}"} over {clustering.get("tests_scored")} tests
(1 = perfect, 0 = chance).

## Per-test results

| Test | Planted cause | Rerun failure rate | Reruns flag it | FlakeLab verdict | FlakeLab cause |
|---|---|---|---|---|---|
{rows_md}

## Threats to validity

- **Planted fixtures.** The causes were designed to be detectable by these exact conditions,
  so this measures whether FlakeLab works as intended, not real-world accuracy.
- **One machine, one run.** CPU-sensitive results depend on the host; repeated evaluations
  on other hardware are needed before generalising.
- **Fixed run budget.** Results change with the number of runs; rare failures need far more.
- **Hidden sensitivities are invisible to reruns by construction** (they never fail at
  baseline), which favours FlakeLab on such tests. That is the point of the method, but the
  size of the advantage depends on how common such tests are in real projects, which this
  benchmark cannot tell us.
"""
    (out / "EVALUATION.md").write_text(report)
