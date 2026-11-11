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


def agglomerative(items: list, distance, threshold: float) -> list[list]:
    """Average-linkage agglomerative clustering.

    Start with every item in its own group; repeatedly merge the two groups whose
    average pairwise distance is smallest, while it is at most `threshold`.
    Pairwise distances are computed once and cached: O(n^2) memory. Each merge
    scans all pairs of groups, so the whole run is O(n^3) time, which is fine for
    hundreds of tests but would need a smarter algorithm for tens of thousands.
    Returns all groups, including single items.
    """
    cache: dict = {}

    def d(a, b):
        key = (a, b) if a <= b else (b, a)
        if key not in cache:
            cache[key] = distance(a, b)
        return cache[key]

    groups = [[item] for item in items]

    def avg_distance(g1, g2):
        return sum(d(a, b) for a in g1 for b in g2) / (len(g1) * len(g2))

    while len(groups) > 1:
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                dist = avg_distance(groups[i], groups[j])
                if best is None or dist < best[0]:
                    best = (dist, i, j)
        if best is None or best[0] > threshold:
            break
        _, i, j = best
        groups[i] = sorted(groups[i] + groups[j])
        del groups[j]
    return groups


def cluster_failures(failure_sets: dict, threshold: float = 0.5) -> list[list[str]]:
    """failure_sets: {test_id: set(run_keys where it failed)}.
    Returns clusters (lists of test ids) with at least 2 members."""
    tests = sorted(t for t, runs in failure_sets.items() if runs)
    groups = agglomerative(
        tests, lambda a, b: jaccard_distance(failure_sets[a], failure_sets[b]), threshold
    )
    return [g for g in groups if len(g) >= 2]


def cluster_similarity(cluster: list[str], failure_sets: dict) -> float:
    """Average Jaccard similarity inside a cluster (1.0 = always fail together)."""
    pairs = [(a, b) for i, a in enumerate(cluster) for b in cluster[i + 1 :]]
    if not pairs:
        return 1.0
    total = sum(
        1 - jaccard_distance(failure_sets.get(a, set()), failure_sets.get(b, set()))
        for a, b in pairs
    )
    return total / len(pairs)
