# Viva and interview preparation

Hard questions an examiner or interviewer may ask, with model answers. Don't memorise the
words: make sure you could explain each answer on a whiteboard.

## Problem and contribution

**1. What problem does FlakeLab solve, in one sentence?**
It finds which environmental conditions (CPU, memory, network, test order, timezone) are
associated with a flaky test's failures, using controlled experiments instead of guessing
from logs.

**2. Tools like BuildPulse and Trunk already handle flaky tests. Why build this?**
They mainly detect and quarantine flaky tests from CI history and infer causes from logs:
observation. FlakeLab intervenes: it changes one variable at a time and measures the effect.
It is not better at scale or integrations; it answers a different question.

**3. Isn't this just Shaker?**
Shaker adds stress to expose flaky tests faster (detection). FlakeLab uses controlled
one-variable arms, statistics with explicit levels of claim, clustering and reproduction
capsules for diagnosis. A 2026 evaluation found Shaker's stress didn't beat plain reruns at
equal budget for detection, which is exactly why we evaluated FlakeLab at equal budget too.

**4. What is your actual contribution?**
The combination: controlled experiments + statistical verdicts + DNA clustering +
statistically verifiable reproduction capsules, in one open tool, evaluated against reruns
at equal budget. Not a world first in any single part.

## Statistics

**5. What does p < 0.001 mean here?**
If the condition made no difference, a result at least this extreme would happen by chance
less than 0.1% of the time. It does not mean "99.9% chance the hypothesis is true".

**6. Why Fisher's exact test and not chi-squared?**
Our counts are tiny (10 runs); chi-squared's approximation needs expected counts of about
5 or more per cell. Fisher's test computes the exact hypergeometric probability.

**7. Why one-sided?**
We only ask whether a condition makes failure *more* likely. A condition that reduces
failures isn't evidence of a sensitivity.

**8. Why Holm-Bonferroni?**
Six comparisons per test at alpha 0.05 give about a 26% chance of at least one false alarm.
Holm controls the family-wise error rate and is uniformly more powerful than plain Bonferroni.

**9. Your experiment found nothing. Is the test fine?**
No. Absence of evidence isn't evidence of absence. With 10 runs only effects of roughly 60%+
are detectable (see the power table). FlakeLab says "unknown" or "weak signal", not "fine".

**10. Why can't you claim CPU is the root cause?**
Limiting CPU changes several things at once: timing, thread interleaving, GC pauses. The
experiment shows the condition matters, not the mechanism. Hence "supported hypothesis".

## Docker and operating systems

**11. How does `--cpus 0.25` actually work?**
Docker writes a CFS quota into the container's cgroup (`cpu.max` = 25000 per 100000 µs).
The kernel scheduler throttles the container's processes once they use 25 ms of CPU in each
100 ms period.

**12. What happens when a test exceeds `--memory 128m`?**
The cgroup's memory controller can't reclaim enough, so the kernel OOM killer kills a process
in the container, usually the one with the largest memory use. Docker then reports
`OOMKilled=true`. FlakeLab's plugin writes results after every test, so even if pytest itself
dies, we know which test was running.

**13. Why a fresh container per run?**
Independence: each run must be a separate sample. Reusing a container could leak files,
caches or state between runs and bias the statistics.

**14. How does FlakeLab get its plugin into any project's image?**
`docker create`, then `docker cp` the plugin folder into the stopped container, then
`docker start`. No image rebuild needed.

**15. What is Docker-out-of-Docker, and the security risk?**
FlakeLab's container mounts `/var/run/docker.sock` and controls the host's Docker engine to
start sibling containers. Anyone with that socket effectively has root on the host, so only
use it on machines you control.

## CI/CD

**16. Walk me through your pipeline.**
Push → quality job (ruff, format, mypy, pytest on Python 3.10 and 3.12) → Docker job (builds,
smoke tests, a real-Docker integration test that checks each condition is applied, capsule
create and verify, Docker-out-of-Docker) → on main, publish images to GHCR. PRs get a short
FlakeLab experiment posted as a comment; a full run and the evaluation run on demand.

**17. How do you stop CI costs exploding?**
Short PR experiments (5 runs per condition, path filters, concurrency groups that cancel old
runs, timeouts); long experiments only on manual dispatch, weekly or tags.

**18. Why `pull_request` and not `pull_request_target`?**
`pull_request_target` runs fork code with write permissions and secrets. That pattern was
behind real 2025–2026 supply-chain attacks on GitHub Actions.

**19. A CI step failed with "denied" when pushing to GHCR. What was it?**
The images had no `org.opencontainers.image.source` label, so the workflow token couldn't
create linked packages. Adding the label fixed it.

## Design and evaluation

**20. Why interleave conditions?**
If all CPU runs happened at the end and the laptop heated up, heat would look like a CPU
effect. Interleaving spreads drift across conditions.

**21. Why default to one worker?**
Parallel runs compete for the same CPUs and contaminate the CPU experiment.

**22. What's the complexity of your clustering?**
Average-linkage agglomerative: O(n²) memory for cached distances and O(n³) time in this
simple implementation. Fine for hundreds of tests; for tens of thousands I'd use a
nearest-neighbour-chain algorithm or a library.

**23. How did you evaluate FlakeLab?**
FlakeBench: 28 tests with planted causes. Same run budget for FlakeLab and plain reruns.
Measured detection, attribution accuracy, false positives, inconclusive rate, reproduction
rate, time and overhead, and DNA clustering quality (Adjusted Rand Index).

**24. Isn't evaluating on your own planted tests circular?**
Partly, yes, and the report says so. It verifies the tool works as designed. Real-world
evidence needs public datasets and real projects, which is the next step.

**25. What would you do with another month?**
Public dataset evaluation, real open-source projects, adaptive run allocation (more runs only
where a signal appears), network latency/loss conditions, support beyond pytest.

## Questions to ask yourself before the viva

- Can I draw the architecture from memory?
- Can I compute a Fisher p-value for 3/3 vs 0/3 by hand?
- Can I explain what a cgroup is to someone who has never heard of Linux?
- Can I explain one bug I hit and how I fixed it? (GHCR denied; order-capsule verification
  comparing against the wrong baseline; 4 runs giving insufficient power in CI.)
