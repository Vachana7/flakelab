"""Failure clustering.

Research (Parry et al., EASE 2025) found that most flaky tests fail together in
clusters that share a root cause. We group tests whose failures happen in the
same runs, so a developer can fix one shared cause instead of many tests.

Method: Jaccard distance between the sets of runs in which two tests failed,
then average-linkage agglomerative clustering (start with every test alone,
keep merging the two closest groups while they are closer than a threshold).
"""

from __future__ import annotations


def jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def cluster_failures(failure_sets: dict, threshold: float = 0.5) -> list[list[str]]:
    """failure_sets: {test_id: set(run_keys where it failed)}.
    Returns clusters (lists of test ids) with at least 2 members."""
    tests = sorted(t for t, runs in failure_sets.items() if runs)
    clusters = [[t] for t in tests]

    def avg_distance(c1, c2):
        total = 0.0
        for a in c1:
            for b in c2:
                total += jaccard_distance(failure_sets[a], failure_sets[b])
        return total / (len(c1) * len(c2))

    while len(clusters) > 1:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = avg_distance(clusters[i], clusters[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None or best[0] > threshold:
            break
        _, i, j = best
        clusters[i] = sorted(clusters[i] + clusters[j])
        del clusters[j]
    return [c for c in clusters if len(c) >= 2]


def cluster_similarity(cluster: list[str], failure_sets: dict) -> float:
    """Average Jaccard similarity inside a cluster (1.0 = always fail together)."""
    pairs = [(a, b) for i, a in enumerate(cluster) for b in cluster[i + 1 :]]
    if not pairs:
        return 1.0
    return sum(1 - jaccard_distance(failure_sets[a], failure_sets[b]) for a, b in pairs) / len(
        pairs
    )
