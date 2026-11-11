"""Turns raw run results into findings.

Three levels of claim, from strongest evidence to weakest, and we never claim
more than the data supports:

* Confirmed observation: a measured fact, e.g. "failed 10/10 runs with CPU
  limited vs 0/10 at baseline, p < 0.001 after correction".
* Supported hypothesis: what the observations suggest about the cause, e.g.
  "resource sensitivity". It is an association, not proof of the root cause.
* Unknown: the test is unreliable, but none of the tested conditions explains it.
"""

from __future__ import annotations

from collections import defaultdict

from flakelab.clustering import cluster_failures, cluster_similarity
from flakelab.conditions import HYPOTHESES, Condition
from flakelab.stats import fisher_one_sided, holm_bonferroni, runs_to_first_failure

FAIL_OUTCOMES = {"failed", "error", "crashed"}

LEVELS = {
    "supported_hypothesis": "Supported hypothesis",
    "weak_signal": "Weak signal (needs more runs)",
    "unknown": "Unknown cause",
    "always_failing": "Always failing (real bug, not flaky)",
    "stable": "Stable",
}


def _fmt_p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"


def short_name(nodeid: str) -> str:
    return nodeid.split("::")[-1]


def analyze(
    runs: list[dict],
    conditions: list[Condition],
    runner=None,
    alpha: float = 0.05,
    expected: dict | None = None,
) -> dict:
    cond_by_name = {c.name: c for c in conditions}
    counts: defaultdict[str, defaultdict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"runs": 0, "failures": 0})
    )
    failure_sets: defaultdict[str, set] = defaultdict(set)
    all_tests = set()

    for run in runs:
        key = f"{run['condition']}#{run['index']}"
        for nodeid, outcome in run["outcomes"].items():
            all_tests.add(nodeid)
            cell = counts[nodeid][run["condition"]]
            cell["runs"] += 1
            if outcome in FAIL_OUTCOMES:
                cell["failures"] += 1
                failure_sets[nodeid].add(key)

    tests = []
    for nodeid in sorted(all_tests):
        per_cond = {}
        for cond in conditions:
            cell = counts[nodeid][cond.name]
            rate = cell["failures"] / cell["runs"] if cell["runs"] else None
            per_cond[cond.name] = {"runs": cell["runs"], "failures": cell["failures"], "rate": rate}
        tests.append(_analyze_test(nodeid, per_cond, conditions, cond_by_name, runner, alpha))

    clusters = _build_clusters(tests, failure_sets)
    result = {"tests": tests, "clusters": clusters, "summary": _summary(tests, clusters)}
    if expected:
        active = {c.category for c in conditions}
        result["evaluation"] = evaluate(tests, expected, active)
    return result


def _analyze_test(nodeid, per_cond, conditions, cond_by_name, runner, alpha):
    base = per_cond.get("baseline", {"runs": 0, "failures": 0, "rate": None})
    b_runs, b_fail = base["runs"], base["failures"]
    b_rate = base["rate"] or 0.0
    total_fail = sum(c["failures"] for c in per_cond.values())

    # 1. Compare every condition with the baseline.
    p_values, raw = {}, {}
    for cond in conditions:
        if cond.name == "baseline":
            continue
        cell = per_cond[cond.name]
        if cell["runs"] == 0 or b_runs == 0:
            continue
        p = fisher_one_sided(cell["failures"], cell["runs"], b_fail, b_runs)
        p_values[cond.name] = p
        raw[cond.name] = cell
    significant = holm_bonferroni(p_values, alpha) if p_values else {}

    observations = []
    for name, p in sorted(p_values.items(), key=lambda kv: kv[1]):
        cell, cond = raw[name], cond_by_name[name]
        if cell["failures"] == 0 and p >= alpha:
            continue
        sig = significant.get(name, False)
        observations.append(
            {
                "condition": name,
                "label": cond.label,
                "category": cond.category,
                "failures": cell["failures"],
                "runs": cell["runs"],
                "baseline_failures": b_fail,
                "baseline_runs": b_runs,
                "p_value": p,
                "significant": sig,
                "text": (
                    f"Failed {cell['failures']}/{cell['runs']} runs with {cond.label} "
                    f"vs {b_fail}/{b_runs} at baseline (p {_fmt_p(p)}"
                    f"{', significant after correction' if sig else ', not significant'})."
                ),
            }
        )

    sig_obs = [o for o in observations if o["significant"]]
    weak_obs = [o for o in observations if not o["significant"] and o["p_value"] < alpha]
    baseline_flaky = 0 < b_fail < b_runs

    # 2. Decide the verdict.
    verdict = {
        "level": "stable",
        "categories": [],
        "title": "Stable",
        "explanation": "Never failed under any tested condition.",
        "fix": None,
    }
    if b_runs and b_fail == b_runs:
        verdict.update(
            level="always_failing",
            title="Always failing",
            explanation="Failed in every baseline run. This looks like a "
            "real bug or a broken test, not flakiness.",
        )
    elif sig_obs:
        cats = sorted({o["category"] for o in sig_obs})
        if len(cats) == 1:
            h = HYPOTHESES[cats[0]]
            title, explanation, fix = h["title"], h["explanation"], h["fix"]
        else:
            title = "Multiple factors: " + ", ".join(HYPOTHESES[c]["title"] for c in cats)
            explanation = " ".join(HYPOTHESES[c]["explanation"] for c in cats)
            fix = " ".join(HYPOTHESES[c]["fix"] for c in cats)
        verdict.update(
            level="supported_hypothesis",
            categories=cats,
            title=title,
            explanation=explanation,
            fix=fix,
        )
    elif weak_obs:
        verdict.update(
            level="weak_signal",
            categories=sorted({o["category"] for o in weak_obs}),
            title="Weak signal",
            explanation="Some conditions show more failures, but not enough "
            "to rule out chance after correction. Run more experiments.",
        )
    elif total_fail > 0:
        verdict.update(
            level="unknown",
            title="Unknown cause",
            explanation="The test is unreliable, but none of the tested "
            "conditions explains its failures. Possible causes: internal "
            "randomness, concurrency inside the test, or a factor FlakeLab "
            "did not test.",
        )

    # 3. A one-command reproduction using the strongest condition.
    reproduce = None
    if sig_obs:
        best = max(sig_obs, key=lambda o: o["failures"] / o["runs"])
        rate = best["failures"] / best["runs"]
        reproduce = {
            "condition": best["condition"],
            "note": (
                "Runs the test on its own, without the earlier tests it depends on."
                if best["category"] == "order"
                else ""
            ),
            "failure_rate": rate,
            "baseline_rate": b_rate,
            "runs_to_failure": runs_to_first_failure(rate),
            "baseline_runs_to_failure": runs_to_first_failure(b_rate),
            "command": runner.reproduce_command(
                next(c for c in conditions if c.name == best["condition"]), nodeid
            )
            if runner
            else None,
        }

    return {
        "nodeid": nodeid,
        "name": short_name(nodeid),
        "per_condition": per_cond,
        "baseline_flaky": baseline_flaky,
        "hidden_sensitivity": bool(sig_obs) and b_fail == 0,
        "observations": observations,
        "verdict": verdict,
        "reproduce": reproduce,
        "cluster": None,
    }


def _build_clusters(tests, failure_sets):
    groups = cluster_failures(dict(failure_sets))
    by_id = {t["nodeid"]: t for t in tests}
    clusters = []
    for i, members in enumerate(groups, start=1):
        cats = defaultdict(int)
        for m in members:
            by_id[m]["cluster"] = i
            for c in by_id[m]["verdict"]["categories"]:
                cats[c] += 1
        shared = [c for c, n in cats.items() if n == len(members)]
        clusters.append(
            {
                "id": i,
                "tests": members,
                "size": len(members),
                "similarity": round(cluster_similarity(members, failure_sets), 2),
                "shared_categories": shared,
                "shared_title": " + ".join(HYPOTHESES[c]["title"] for c in shared)
                if shared
                else "Co-failing tests (shared cause not identified)",
            }
        )
    return clusters


def _summary(tests, clusters):
    levels = defaultdict(int)
    for t in tests:
        levels[t["verdict"]["level"]] += 1
    return {
        "tests": len(tests),
        "baseline_flaky": sum(t["baseline_flaky"] for t in tests),
        "hidden_sensitivities": sum(t["hidden_sensitivity"] for t in tests),
        "supported_hypotheses": levels["supported_hypothesis"],
        "unknown": levels["unknown"],
        "weak_signals": levels["weak_signal"],
        "always_failing": levels["always_failing"],
        "stable": levels["stable"],
        "clusters": len(clusters),
    }


def evaluate(tests: list[dict], expected: dict, active_categories: set | None = None) -> dict:
    """Compare verdicts with known ground truth (only possible on test fixtures
    whose causes we planted). This checks that FlakeLab works as designed; it is
    not evidence of how well it works on real-world projects."""
    rows, correct, scored = [], 0, 0
    found_by_reruns = found_by_flakelab = 0
    sensitive = 0
    for t in tests:
        exp = expected.get(t["nodeid"])
        if exp is None:
            continue
        v = t["verdict"]
        if (
            active_categories is not None
            and exp not in ("stable", "intrinsic")
            and exp not in active_categories
        ):
            rows.append(
                {"nodeid": t["nodeid"], "expected": exp, "predicted": "not tested", "correct": None}
            )
            continue
        if exp == "stable":
            ok = v["level"] == "stable"
        elif exp == "intrinsic":
            ok = v["level"] == "unknown"
        else:
            ok = v["level"] == "supported_hypothesis" and exp in v["categories"]
        scored += 1
        correct += ok
        if exp not in ("stable",):
            sensitive += 1
            found_by_reruns += t["per_condition"]["baseline"]["failures"] > 0
            found_by_flakelab += v["level"] in ("supported_hypothesis", "unknown", "weak_signal")
        predicted = ", ".join(v["categories"]) if v["categories"] else v["level"]
        rows.append({"nodeid": t["nodeid"], "expected": exp, "predicted": predicted, "correct": ok})
    return {
        "rows": rows,
        "accuracy": correct / scored if scored else None,
        "correct": correct,
        "scored": scored,
        "problem_tests": sensitive,
        "visible_to_baseline_reruns": found_by_reruns,
        "found_by_flakelab": found_by_flakelab,
    }
