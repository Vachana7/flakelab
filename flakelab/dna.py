"""Failure DNA (Pillar B): group tests by their experimental signature.

A test's *signature* is its failure rate under every condition, e.g.

    baseline  cpu  memory  network  reverse  shuffled  timezone
      0.1     0.0   0.0     1.0      0.0      0.0       0.0       <- a network test

Two kinds of grouping answer two different questions:

* Co-failure clusters (clustering.py): "do these tests fail in the SAME RUNS?"
  That suggests a shared runtime event (one slow service hits both tests).
* DNA clusters (this module): "do these tests react to the SAME CONDITIONS?"
  That suggests a shared kind of weakness (both assume network access), even if
  their failures happen at different moments.

Neither proves a shared root cause. They tell a developer where to look first.

Distance between signatures: the largest difference in failure rate under any
single condition (Chebyshev distance). Tests only group together if they behave
alike under EVERY condition, so one condition that separates them keeps them apart.
"""

from __future__ import annotations

from collections import Counter
from math import comb

from flakelab.clustering import agglomerative, cluster_similarity

DNA_THRESHOLD = 0.4  # max per-condition failure-rate difference inside a cluster


def signature(test: dict, condition_names: list[str]) -> list[float]:
    rates = []
    for name in condition_names:
        cell = test["per_condition"].get(name) or {}
        rates.append(cell["failures"] / cell["runs"] if cell.get("runs") else 0.0)
    return rates


def chebyshev(a: list[float], b: list[float]) -> float:
    return max((abs(x - y) for x, y in zip(a, b, strict=True)), default=0.0)


def adjusted_rand_index(truth: list, predicted: list) -> float | None:
    """Agreement between two groupings, corrected for chance (Hubert & Arabie, 1985).

    1.0 = identical groupings, about 0 = no better than random, can be negative.
    """
    n = len(truth)
    if n < 2:
        return None
    pairs = Counter(zip(truth, predicted, strict=True))
    a = Counter(truth)
    b = Counter(predicted)
    index = sum(comb(c, 2) for c in pairs.values())
    sum_a = sum(comb(c, 2) for c in a.values())
    sum_b = sum(comb(c, 2) for c in b.values())
    total = comb(n, 2)
    expected = sum_a * sum_b / total
    maximum = (sum_a + sum_b) / 2
    if maximum == expected:
        return 1.0 if index == expected else 0.0
    return (index - expected) / (maximum - expected)


def _common_prefix(paths: list[str]) -> str | None:
    files = {p.split("::")[0] for p in paths}
    return files.pop() if len(files) == 1 else None


def build_dna(
    tests: list[dict],
    conditions: list,
    failure_sets: dict,
    expected: dict | None = None,
) -> dict:
    names = [c.name for c in conditions]
    labels = {c.name: c.label for c in conditions}
    investigated = [t for t in tests if t["verdict"]["level"] not in ("stable", "always_failing")]
    sigs = {t["nodeid"]: signature(t, names) for t in investigated}
    for t in tests:
        t["dna"] = [round(x, 3) for x in signature(t, names)]

    groups = agglomerative(sorted(sigs), lambda a, b: chebyshev(sigs[a], sigs[b]), DNA_THRESHOLD)
    by_id = {t["nodeid"]: t for t in tests}
    clusters = []
    for gid, members in enumerate((g for g in groups if len(g) >= 2), start=1):
        member_tests = [by_id[m] for m in members]
        mean = [sum(sigs[m][i] for m in members) / len(members) for i in range(len(names))]
        spread = max(
            max(sigs[m][i] for m in members) - min(sigs[m][i] for m in members)
            for i in range(len(names))
        )
        significant_sets = [
            {o["condition"] for o in t["observations"] if o["significant"]} for t in member_tests
        ]
        common = set.intersection(*significant_sets) if significant_sets else set()
        evidence = []
        for cond in sorted(common):
            ps = [
                o["p_value"]
                for t in member_tests
                for o in t["observations"]
                if o["condition"] == cond
            ]
            evidence.append(
                {
                    "condition": cond,
                    "label": labels[cond],
                    "members_significant": len(ps),
                    "max_p_value": max(ps),
                }
            )
        co_fail = cluster_similarity(members, failure_sets) if failure_sets else None
        if common and spread <= 0.2:
            confidence = "high"
        elif common:
            confidence = "medium"
        else:
            confidence = "low"
        for t in member_tests:
            t["dna_cluster"] = gid
        clusters.append(
            {
                "id": gid,
                "size": len(members),
                "tests": members,
                "signature": [round(x, 3) for x in mean],
                "spread": round(spread, 3),
                "common_conditions": [labels[c] for c in sorted(common)],
                "evidence": evidence,
                "co_failure_similarity": round(co_fail, 2) if co_fail is not None else None,
                "shared_file": _common_prefix(members),
                "confidence": confidence,
                "interpretation": _interpret(common, labels, co_fail),
                "limitations": (
                    "Tests are grouped by similar behaviour under the tested conditions. A "
                    "shared signature suggests a shared kind of weakness; it does not prove "
                    "a shared root cause. Signatures from few runs are noisy."
                ),
            }
        )
    for t in tests:
        t.setdefault("dna_cluster", None)

    result = {"conditions": names, "threshold": DNA_THRESHOLD, "clusters": clusters}
    if expected:
        result["quality"] = _quality(investigated, expected)
    return result


def _interpret(common: set, labels: dict, co_fail: float | None) -> str:
    if not common:
        return "Similar failure rates, but no condition is significant for every member."
    conds = ", ".join(labels[c] for c in sorted(common))
    if co_fail is not None and co_fail >= 0.5:
        return (
            f"All members react to {conds} and usually fail in the same runs: "
            "likely one shared dependency or event."
        )
    return (
        f"All members react to {conds}, but often fail in different runs: "
        "likely the same kind of weakness in separate places."
    )


def _quality(investigated: list[dict], expected: dict) -> dict:
    """How well DNA clusters match the planted causes (Adjusted Rand Index)."""
    truth, predicted = [], []
    singleton = 1000
    for t in investigated:
        exp = expected.get(t["nodeid"])
        if exp is None or exp == "stable":
            continue
        truth.append(exp if isinstance(exp, str) else "+".join(sorted(exp)))
        if t.get("dna_cluster"):
            predicted.append(t["dna_cluster"])
        else:
            singleton += 1
            predicted.append(singleton)
    return {
        "tests_scored": len(truth),
        "adjusted_rand_index": adjusted_rand_index(truth, predicted),
        "note": "Compares DNA clusters with the planted causes of the fixtures "
        "(1 = perfect agreement, 0 = chance level).",
    }
