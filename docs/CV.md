# CV and portfolio text (only verified claims)

Every number below comes from a recorded run linked in `docs/evaluation/` or
`docs/recorded-run/`. If you change the project, re-check the numbers before using them.

## One-line version

**FlakeLab**: experimental root-cause investigation for flaky CI tests (Python, Docker, GitHub Actions)

## CV bullets (pick 2–3)

- Built **FlakeLab**, an open-source tool that diagnoses flaky Python tests by re-running them
  in fresh Docker containers while changing one condition at a time (CPU, memory, network,
  test order, timezone), with Fisher exact tests and Holm-Bonferroni correction.
- In an equal-budget evaluation on 28 known-cause fixtures (GitHub-hosted runners, real
  Docker), FlakeLab flagged **17/17** problem tests vs **5/17** for plain reruns, attributed the
  planted cause for **27/28** tests with **0** false positives on 11 stable controls, and
  reported its one miss as a "weak signal" rather than guessing.
- Designed **reproduction capsules** that record a failing test order, Docker limits, image
  identity and package versions, replayable with one command and verifiable statistically;
  verified on real Docker in CI.
- Built a CI/CD pipeline in **GitHub Actions**: lint, type checks and tests on two Python
  versions, Docker image builds, a real-Docker integration test, automated PR reports, and
  image publishing to GitHub Container Registry.

## Short project description (portfolio / application form)

FlakeLab investigates why tests fail intermittently. Instead of inferring causes from CI logs,
it runs controlled experiments: the test suite is executed repeatedly in fresh containers
while exactly one environmental variable changes, and statistical tests decide which
conditions are associated with each test's failures. Conclusions are labelled as confirmed
observations, supported hypotheses or unknown. Failure DNA groups tests that react to the
same conditions, and reproduction capsules let anyone replay and verify a diagnosis.
I evaluated it against plain reruns at the same run budget on fixtures with known causes,
including documenting where it falls short (a marginal CPU sensitivity needs more runs; one
DNA cluster mixed unrelated low-rate tests).

## Things not to claim

- Not "the first" flaky-test tool; Shaker and iDFlakies cover parts of this.
- Not "finds root causes": it finds conditions associated with failures.
- Not evaluated on real-world projects or public datasets yet (planned).
- Not production-scale.
