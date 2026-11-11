"""Statistics, written from scratch so FlakeLab needs no extra packages.

Fisher's exact test answers: "If the condition made NO difference, how likely
is it that we would see this many failures under the condition just by luck?"
That probability is the p-value. A small p-value (below 0.05) means luck is an
unlikely explanation.

Because each test is compared under several conditions, we also apply the
Holm-Bonferroni correction. Without it, testing 6 conditions at 0.05 each
would give roughly a 26% chance of at least one false alarm per test.
"""

from __future__ import annotations

from math import comb


def fisher_one_sided(cond_fail: int, cond_runs: int, base_fail: int, base_runs: int) -> float:
    """One-sided Fisher exact test: is the failure rate under the condition
    GREATER than under the baseline?

    Uses the hypergeometric distribution: out of all runs (N) there were K
    failures in total; if failures were spread randomly, what is the chance
    that the condition's n runs received `cond_fail` or more of them?
    """
    if cond_runs <= 0 or base_runs <= 0:
        return 1.0
    total = cond_runs + base_runs  # N
    failures = cond_fail + base_fail  # K
    denominator = comb(total, cond_runs)
    p = 0.0
    for x in range(cond_fail, min(cond_runs, failures) + 1):
        p += comb(failures, x) * comb(total - failures, cond_runs - x) / denominator
    return min(1.0, p)


def holm_bonferroni(p_values: dict, alpha: float = 0.05) -> dict:
    """Return {key: True/False} saying which results stay significant after
    Holm-Bonferroni correction for multiple comparisons."""
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    significant = {key: False for key in p_values}
    for rank, (key, p) in enumerate(ordered):
        if p <= alpha / (m - rank):
            significant[key] = True
        else:
            break  # once one fails, all larger p-values fail too
    return significant


def runs_to_first_failure(failure_rate: float) -> float | None:
    """Expected number of runs until a failure is seen (geometric distribution)."""
    if failure_rate <= 0:
        return None
    return 1.0 / failure_rate
