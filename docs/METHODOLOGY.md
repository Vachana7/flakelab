# FlakeLab methodology

## Question

For a test suite, which environmental conditions are *associated* with each test's
failures? FlakeLab answers with controlled experiments rather than inference from logs.

## Experimental design

1. **Baseline.** Normal resources, network on, default test order, `TZ=UTC0`. The baseline
   pins every variable FlakeLab later changes.
2. **One change per condition.**

   | Condition | Mechanism | What actually happens |
   |---|---|---|
   | CPU 0.25 core | `docker --cpus 0.25` | Linux CFS quota: the container gets 25 ms of CPU per 100 ms period (cgroup `cpu.max`), so CPU work takes about 4x longer in wall time |
   | Memory 128 MB | `docker --memory 128m --memory-swap 128m` | cgroup memory limit with no swap; exceeding it triggers the kernel OOM killer inside the container |
   | Network off | `docker --network none` | the container gets only a loopback interface: no DNS, no routes |
   | Reverse order | plugin reverses collected tests | shared state between tests becomes visible |
   | Shuffled order | plugin shuffles with a recorded seed | as above, different random orders, reproducible from the seed |
   | Timezone UTC+5:30 | `TZ=IST-5:30` (POSIX string) | C library local time changes; works without a timezone database |

3. **Repetition.** R runs per condition (default 10). Each run is a fresh container.
4. **Interleaving.** The schedule cycles through all conditions (B, C, M, N, R, S, T, B, C, ...)
   so slow drift on the host is spread evenly instead of masquerading as an effect.
5. **Measurement.** Per run, the plugin records every test's outcome and the collection order,
   writing after each test so a crash still attributes the failure to the running test.

## Statistics

For each test and condition, a 2x2 table (failed/passed x condition/baseline) is tested with
a **one-sided Fisher exact test** (H1: the condition makes failure more likely). Fisher's test
is exact for small counts, where chi-squared approximations are unreliable.

Each test is compared under six conditions, so p-values are corrected with
**Holm-Bonferroni** at alpha = 0.05 (family = the six comparisons of one test).

### Power

The table shows the smallest failure count under a condition that can reach significance for
the *strongest* comparison of a test (threshold alpha/6 = 0.0083):

| Runs per condition | Smallest detectable result (vs 0 failures at baseline) | Same, if baseline fails once |
|---|---|---|
| 3 | never | never |
| 5 | 5/5 (100%) | never |
| 6 | 5/6 (83%) | 6/6 (100%) |
| 8 | 6/8 (75%) | 7/8 (88%) |
| 10 | 6/10 (60%) | 8/10 (80%) |
| 15 | 7/15 (47%) | 8/15 (53%) |
| 20 | 7/20 (35%) | 9/20 (45%) |
| 30 | 7/30 (23%) | 9/30 (30%) |

Consequence: with the default 10 runs, only strong sensitivities are attributed. Weaker ones
appear as "weak signal" or "unknown", by design.

## Levels of claim

| Level | Meaning | Example |
|---|---|---|
| Confirmed observation | a measured, statistically significant difference | failed 10/10 with CPU 0.25 core vs 0/10 at baseline, p < 0.001 after correction |
| Supported hypothesis | what the observations suggest about the cause | resource sensitivity (CPU / timing) |
| Weak signal | p < 0.05 before correction only | run more experiments |
| Unknown | unreliable, but no tested condition explains it | internal randomness, untested factor |
| Always failing | fails in every baseline run | a real bug, not flakiness |

A supported hypothesis is never presented as the root cause. Restricting CPU can also change
thread interleavings, garbage-collection timing and more; the experiment shows that the
condition matters, not which mechanism inside the test is responsible.

## Failure DNA

A test's DNA is its vector of failure rates across conditions. DNA clusters group tests whose
vectors are within 0.4 of each other under *every* condition (Chebyshev distance,
average-linkage agglomerative clustering). Co-failure groups, separately, group tests that
fail in the *same runs* (Jaccard distance on run sets). Both point to where to look; neither
proves a shared cause.

## Reproduction capsules

For each investigated failure FlakeLab picks a recorded failing run under the identified
condition and stores the exact order prefix (tests that ran before, plus the failing test),
the condition's Docker flags and environment, image identity (tag, id, registry digests),
Python and package versions, repository revision and host details. `capsule verify` re-runs
the capsule against a baseline, interleaved, and applies the same Fisher test. For
order-dependent failures the baseline arm runs the default order, because the order itself is
the condition.

## Known confounders and limitations

- **Host load.** Other programs on the machine affect timing. Mitigated by interleaving and
  one worker; not eliminated. CPU results are host-specific.
- **Container start-up variance.** Measured and reported as per-run overhead.
- **Condition overlap.** `--memory` limits can slow memory-heavy code; `--network none` also
  removes DNS. Each condition is "one Docker setting", which may change more than one thing
  inside the program.
- **Multiple tests share runs.** Tests in one run are not independent samples of each other;
  this matters for co-failure analysis, not for per-test Fisher tests.
- **Run-count limits** (see the power table).
- **Locale** is not tested: Python's UTF-8 locale coercion (PEP 538) makes locale changes in
  slim images nearly ineffective, so a locale condition would mostly measure nothing.
- **Network disruption** (latency, loss) is not tested yet; only isolation.
