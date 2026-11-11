# Lesson 1: Flaky tests, controlled experiments and hypothesis testing

**Code for this lesson:** `flakelab/stats.py`, `flakelab/analyzer.py`, `flakelab/conditions.py`

## A. Fundamentals

A test is a function that checks the code. We expect it to be **deterministic**: same code,
same result. A **flaky** test breaks that promise, because its result depends on something
other than the code: time, CPU speed, the network, other tests, randomness.

Plain reruns can tell you *that* a test is flaky (it passed once and failed once). They can't
tell you *why*, because in a rerun everything varies at once and nothing is controlled.

A **controlled experiment** fixes everything except one variable. If the outcome changes
when only that variable changes, the variable is *associated* with the outcome. That's the
whole idea of FlakeLab: `conditions.py` defines a baseline that pins every variable we
study (`BASELINE_ENV` pins `TZ=UTC0` and the default order), and each condition changes
exactly one of them.

## B. Theory: from counts to evidence

Suppose `test_payment` failed 9/10 runs with limited CPU and 0/10 at baseline. Could that be
luck? Statistics turns that question into a number.

- **Null hypothesis (H0):** the condition makes no difference.
- **p-value:** if H0 were true, the probability of seeing a result at least this extreme.
- **Significance level (alpha = 0.05):** if p < alpha, we reject H0. We accept a 5% chance of
  a false alarm (a **Type I error**). Missing a real effect is a **Type II error**.

**Fisher's exact test.** Put the counts in a 2x2 table:

|            | failed | passed |
|------------|--------|--------|
| condition  | a = 9  | b = 1  |
| baseline   | c = 0  | d = 10 |

Across all 20 runs there were K = a + c = 9 failures. If the condition made no difference,
those 9 failures would land in the 20 runs at random, like drawing 10 cards (the condition's
runs) from a deck of 20 that has 9 red cards. The number of red cards you draw follows the
**hypergeometric distribution**:

```
P(X = x) = C(K, x) * C(N - K, n - x) / C(N, n)      N = 20 runs, n = 10 condition runs
```

The one-sided p-value is P(X >= 9): the chance the condition gets 9 or more of the failures
by luck. Look at `fisher_one_sided()` in `stats.py`: the loop adds up exactly this sum.
It's "exact" because it computes the probability directly instead of approximating it
(the chi-squared test approximates and is unreliable with small counts like ours).

**Why one-sided?** We only care whether a condition makes failures *more* likely.

**Multiple comparisons.** We test 6 conditions per test. At alpha = 0.05 each, the chance of
at least one false alarm is 1 - 0.95^6 ≈ 26%. **Holm-Bonferroni** fixes this: sort the
p-values from smallest to largest and compare the i-th smallest with alpha / (m - i).
Stop at the first one that fails. See `holm_bonferroni()`.

**Statistical power.** With 10 runs per condition, the smallest effect that can survive the
correction is about 6/10 vs 0/10. A test that fails 10% of the time can never be "proven"
with 10 runs. This is why FlakeLab says "weak signal" or "unknown" instead of guessing.

## C. In our code

`analyzer._analyze_test()` does, for each test:
1. count failures per condition,
2. compute a Fisher p-value for each condition against the baseline,
3. apply Holm-Bonferroni,
4. turn significant conditions into a verdict, choosing the claim level carefully:
   observation (measured), hypothesis (suggested cause), unknown.

## D. Design decisions

- **Implemented from scratch** instead of importing scipy: zero dependencies, and you can
  explain every line in a viva. The unit tests check our numbers against scipy reference values.
- **Interleaved schedule** (`experiment.build_schedule`): if all CPU runs came last and the
  laptop got hot, heat would look like a CPU effect. Interleaving spreads drift over all conditions.

## E. Alternatives we rejected

- **Chi-squared test:** inaccurate when expected counts are below 5, which is always our case.
- **Comparing raw failure rates with a fixed threshold** ("> 50% means guilty"): ignores
  sample size, so 1/1 would look as strong as 10/10.
- **Bonferroni (plain):** simpler but more conservative than Holm, so it misses more real effects.

## F. Complexity

Per test and condition, the Fisher sum has at most min(n, K) + 1 terms, so O(n) per
comparison and O(T * C * n) overall for T tests, C conditions and n runs. That's trivial
next to the cost of running containers.

## G. Edge cases

- Baseline fails every run → not flaky, a real bug ("always failing").
- A condition has zero runs (skipped by the local runner) → no comparison, no p-value.
- Fewer failures under a condition than at baseline → one-sided p = 1, never significant.

## H. Interview questions (try answering out loud)

1. What exactly does a p-value of 0.001 mean? What does it *not* mean?
2. Why can't FlakeLab claim CPU starvation *is* the root cause, even with p < 0.001?
3. Why does testing more conditions require a correction? What's the cost of correcting?
4. Your experiment found nothing significant. Does that mean the test is fine?
5. Why use a fresh container for every run instead of reusing one?

## I. Exercises

1. By hand: compute the one-sided Fisher p-value for 3/3 vs 0/3. Then run
   `python -c "from flakelab.stats import fisher_one_sided as f; print(f(3,3,0,3))"` to check.
   Would that result survive Holm-Bonferroni with 6 conditions?
2. Change `--runs` to 4 in a local run of the demo. Which findings disappear, and why?
3. Find the line in `analyzer.py` that decides a test is "hidden sensitivity". Explain it in
   one sentence.
