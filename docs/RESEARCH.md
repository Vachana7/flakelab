# Prior work and FlakeLab's contribution

Written to survive questioning: what exists, what FlakeLab adds, and what it does not claim.
Tool capabilities are summarised from public papers and vendor material as of November 2026
and were not independently tested. Re-check the sources before quoting a number.

## Evidence that the problem matters

| Source | Finding | Caveat |
|---|---|---|
| Google Testing Blog (2016) | about 16% of tests showed some flakiness; 84% of pass-to-fail transitions in CI involved a flaky test | Google-internal, 2016; not an industry-wide figure |
| Atlassian engineering (2025) | flaky tests in the Jira backend cost over 150,000 developer hours a year | one company's estimate |
| Harness, State of software delivery (2026) | most respondents report pipelines affected by flaky tests and failed deployments | survey; self-reported |
| JetBrains, State of CI/CD (2026) | AI-generated changes make flaky tests and unclear feedback more visible and costly | survey |

## Research FlakeLab builds on

| Work | What it found or built | How FlakeLab uses it |
|---|---|---|
| Silva et al., *Effects of computational resources on flaky tests* (FSE 2025) | 46.5% of flaky tests in their dataset were resource-affected (RAFTs); adjusting CPU/memory changes flaky behaviour | motivates the CPU and memory conditions and resource-limited experiments with Docker |
| Parry et al., *Systemic flakiness* (EASE 2025) | 75% of flaky tests belonged to clusters (mean size 13.5) sharing root causes; networking and external dependencies were prominent | motivates co-failure groups, Failure DNA and the network condition |
| Shaker (Silva, Teixeira, d'Amorim) | adds CPU/memory stress while running tests to expose flaky tests faster; available as a GitHub Action | closest prior work on resource perturbation for *detection* |
| 2026 evaluation of Shaker on Python projects | reported that stress injection did not significantly outperform plain reruns at the same execution budget | a warning: perturbation is not automatically better; FlakeLab must be evaluated at equal budget (it is, see EVALUATION) |
| iDFlakies (Lam et al.) | reruns tests in original and random orders to classify order-dependent vs non-order-dependent flaky tests | FlakeLab's reverse and shuffled conditions; victim/polluter and brittle fixtures in FlakeBench |

## Tools engineers use

| Tool | What it does (per public material) |
|---|---|
| BuildPulse | flaky-test detection from CI history, root-cause analysis, quarantine |
| Trunk Flaky Tests | detection, investigation, quarantine, GitHub integration |
| TestDino | flaky detection, ML-based root-cause classification, failure grouping |

## Comparison matrix

✓ = core capability, ◐ = partial or different approach, ✗ = not a goal. Based on public material, not hands-on testing.

| Capability | BuildPulse / Trunk / TestDino | Shaker | iDFlakies | FlakeLab |
|---|---|---|---|---|
| Detection of flaky tests | ✓ (from CI history) | ✓ (reruns under stress) | ✓ (reruns, orders) | ✓ (reruns under conditions) |
| Controlled intervention (change one variable) | ✗ (observational) | ◐ (adds noise/stress, not one controlled variable per arm) | ◐ (order only) | ✓ |
| Environmental experiments (CPU, memory, network, order, timezone) | ✗ | ◐ (CPU/memory stress) | ◐ (order) | ✓ (six conditions) |
| Statistical analysis of the difference | ◐ (failure rates) | ✗ / ◐ | ◐ | ✓ (Fisher exact + Holm-Bonferroni, explicit levels of claim) |
| Failure clustering | ◐ (grouping by error) | ✗ | ✗ | ✓ (co-failure + experimental-signature DNA) |
| Reproducibility package | ✗ / ◐ | ✗ | ◐ (orders) | ✓ (capsules with statistical verify) |
| CI/CD integration | ✓ (SaaS, mature) | ✓ (GitHub Action) | ◐ (research tool) | ✓ (Actions workflows, PR comments) |
| Maturity, scale, language support | ✓ production | research | research | ✗ student prototype, Python/pytest only |

## FlakeLab's contribution, stated precisely

FlakeLab combines, in one open tool for Python projects:

1. **Controlled, one-variable-at-a-time experiments** in fresh containers, rather than
   inference from historical logs or undifferentiated stress.
2. **Explicit statistical claims** (Fisher exact test with multiple-comparison correction)
   with three levels: observation, hypothesis, unknown.
3. **Two complementary groupings**: co-failure (same runs) and Failure DNA (same conditions).
4. **Reproduction capsules** that replay a recorded failing order under the identified
   condition and can be re-verified statistically by anyone.
5. **An equal-budget evaluation** against plain reruns on known-cause fixtures.

## What FlakeLab does not claim

- It is not the first tool to perturb resources (Shaker) or test orders (iDFlakies).
- It does not prove root causes; it reports associations from controlled experiments.
- It has not been evaluated on public flaky-test datasets or large real-world projects yet.
- It does not match the scale, language coverage or integrations of commercial tools.

## Next research steps (after the expo)

1. Run on a public Python flaky-test dataset with labelled causes and report accuracy separately.
2. Run on 3-5 real open-source projects and report findings separately (category 3).
3. Adaptive experiments: spend more runs only on conditions that show a signal.
4. Network disruption (latency, packet loss) as a condition.
