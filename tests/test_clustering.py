from flakelab.clustering import cluster_failures, cluster_similarity, jaccard_distance


def test_jaccard_distance():
    assert jaccard_distance({1, 2}, {1, 2}) == 0
    assert jaccard_distance({1}, {2}) == 1
    assert jaccard_distance({1, 2}, {2, 3}) == 1 - 1 / 3


def test_tests_that_fail_together_are_clustered():
    sets = {
        "a": {"net#1", "net#2", "net#3"},
        "b": {"net#1", "net#2", "net#3", "base#4"},
        "c": {"cpu#1", "cpu#2"},
        "d": set(),
    }
    clusters = cluster_failures(sets)
    assert clusters == [["a", "b"]]
    assert cluster_similarity(["a", "b"], sets) == 0.75


def test_unrelated_failures_are_not_clustered():
    assert cluster_failures({"a": {1, 2}, "b": {3, 4}, "c": {5}}) == []
