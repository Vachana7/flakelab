import math

import pytest

from flakelab.stats import fisher_one_sided, holm_bonferroni, runs_to_first_failure


def test_fisher_no_difference_is_not_significant():
    assert fisher_one_sided(0, 10, 0, 10) == 1.0
    assert fisher_one_sided(1, 10, 1, 10) > 0.5


def test_fisher_matches_hand_calculation():
    # 6/10 failures vs 0/10: P = C(10,6) / C(20,6) = 210 / 38760
    assert math.isclose(fisher_one_sided(6, 10, 0, 10), 210 / 38760)


def test_fisher_matches_scipy_reference_values():
    # Reference values from scipy.stats.fisher_exact(..., alternative="greater")
    assert fisher_one_sided(10, 10, 0, 10) == pytest.approx(5.4125e-06, rel=1e-3)
    assert fisher_one_sided(5, 10, 0, 10) == pytest.approx(0.016254, rel=1e-3)
    assert fisher_one_sided(10, 10, 1, 10) == pytest.approx(5.9538e-05, rel=1e-3)


def test_fisher_is_one_sided():
    # Fewer failures under the condition than at baseline is never "significant".
    assert fisher_one_sided(0, 10, 8, 10) == 1.0


def test_holm_bonferroni():
    result = holm_bonferroni({"a": 0.001, "b": 0.02, "c": 0.04}, alpha=0.05)
    # a: 0.001 <= 0.05/3 yes; b: 0.02 <= 0.05/2 yes; c: 0.04 <= 0.05 yes
    assert result == {"a": True, "b": True, "c": True}
    result = holm_bonferroni({"a": 0.001, "b": 0.03, "c": 0.04}, alpha=0.05)
    assert result == {"a": True, "b": False, "c": False}


def test_runs_to_first_failure():
    assert runs_to_first_failure(0) is None
    assert runs_to_first_failure(0.25) == 4
