from fakes import SimulatedRunner
from test_analyzer import EXPECTED

from flakelab.benchmark import run_benchmark


def test_benchmark_compares_arms_at_equal_budget(tmp_path):
    m = run_benchmark(SimulatedRunner(), 10, EXPECTED, tmp_path, log=lambda *a: None)
    assert m["budget_per_arm"] == 70
    det = m["detection"]
    # Hidden sensitivities (cpu, memory, timezone, order) never fail at baseline,
    # so plain reruns cannot flag them; FlakeLab can.
    assert det["flakelab_environmental"] > det["reruns_environmental"]
    assert m["false_positives"]["flakelab_rate"] == 0
    assert m["diagnosis"]["accuracy_all"] == 1.0
    for name in ("EVALUATION.md", "metrics.json", "chart-detection.svg", "chart-reproduction.svg"):
        assert (tmp_path / name).exists()
    assert "Planted fixtures" in (tmp_path / "EVALUATION.md").read_text()
    assert (tmp_path / "chart-detection.svg").read_text().startswith("<svg")
