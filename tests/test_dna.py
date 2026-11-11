import pytest
from fakes import SimulatedRunner
from test_analyzer import EXPECTED

from flakelab.conditions import ALL_CONDITIONS
from flakelab.dna import adjusted_rand_index, chebyshev
from flakelab.experiment import Experiment


def test_chebyshev_uses_the_largest_single_difference():
    assert chebyshev([0.1, 0, 1.0], [0.2, 0, 1.0]) == pytest.approx(0.1)
    assert chebyshev([0, 1.0, 0], [0, 0, 1.0]) == 1.0


def test_adjusted_rand_index_reference_values():
    assert adjusted_rand_index(["a", "a", "b", "b"], [1, 1, 2, 2]) == 1.0
    assert adjusted_rand_index(["a", "a", "b", "b"], [5, 5, 9, 9]) == 1.0  # names don't matter
    assert adjusted_rand_index(["a", "a", "b", "b"], [1, 2, 1, 2]) == pytest.approx(-0.5)
    # Classic example: sklearn.metrics.adjusted_rand_score gives 0.2424...
    truth = [0, 0, 0, 1, 1, 1]
    pred = [0, 0, 1, 1, 2, 2]
    assert adjusted_rand_index(truth, pred) == pytest.approx(0.24242424, rel=1e-6)


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    exp = Experiment(
        SimulatedRunner(),
        ALL_CONDITIONS,
        runs=10,
        out_dir=tmp_path_factory.mktemp("dna"),
        expected=EXPECTED,
        log=lambda *a: None,
        capsules=False,
    )
    return exp.run()


def members(doc):
    return [{t.split("::")[-1] for t in c["tests"]} for c in doc["dna"]["clusters"]]


def test_tests_with_the_same_weakness_share_dna(doc):
    groups = members(doc)
    assert {"test_reserve_stock", "test_low_stock_alert"} in groups
    assert {"test_delivery_forecast", "test_weather_alerts"} in groups
    # Different weaknesses never share a cluster.
    for g in groups:
        assert not ({"test_authorize_within_sla", "test_export_catalog"} <= g)


def test_dna_cluster_reports_evidence_and_confidence(doc):
    weather = next(c for c in doc["dna"]["clusters"] if "Network off" in c["common_conditions"])
    assert weather["confidence"] == "high"
    assert weather["evidence"][0]["members_significant"] == 2
    assert weather["co_failure_similarity"] > 0.5  # they fail in the same runs
    assert weather["shared_file"] == "tests/test_weather.py"
    assert "does not prove" in weather["limitations"]


def test_every_test_has_a_signature(doc):
    for t in doc["tests"]:
        assert len(t["dna"]) == len(ALL_CONDITIONS)


def test_dna_quality_against_planted_causes(doc):
    quality = doc["dna"]["quality"]
    assert quality["tests_scored"] == 8
    assert quality["adjusted_rand_index"] == pytest.approx(1.0)
