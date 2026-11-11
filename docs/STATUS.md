# FlakeLab engineering status

Living record of what is done, verified, outstanding and blocked. Updated at the end of
every work session. "Verified" means a command was actually run and its output checked.

## Last update: 2026-11-11 (evening)

### Verified (a command was run and its output checked)
| What | Evidence |
|---|---|
| 37 unit/integration tests, lint, format, types | local + CI quality job on Python 3.10 and 3.12 |
| Docker conditions applied correctly | CI integration step: network 3/3, memory 3/3, CPU 3/3 failures; stable control 0/3 |
| Docker-out-of-Docker | CI step runs FlakeLab from its own container |
| Reproduction capsules on real Docker | CI run 43050555008: network capsule 6/6 vs 1/6 (p = 0.0076), order capsule 6/6 vs 0/6 (p = 0.0011); one-shot `reproduce.sh` showed the failure |
| Full demo experiment on real Docker | run 43053496319: 13/13 diagnoses correct, saved in `docs/recorded-run/` |
| Evaluation on FlakeBench (equal budget) | run 43053492029: FlakeLab 17/17 vs reruns 5/17 problem tests flagged; 27/28 correct attributions; 0 false positives; DNA ARI 0.68 |
| PR report | FlakeLab commented on PR #1 automatically |
| Image publishing to GHCR | flakelab, flakelab-demo, flakelab-weather-api |
| Dashboard v2 | headless Chrome screenshots, no console errors |

### Not verified yet
| What | Plan |
|---|---|
| `docker compose up` on Vivek's Windows laptop | Vivek runs it (EXPO.md checklist) |
| GitHub Pages dashboard | needs Pages enabled by the repo owner (optional) |

### Known limitations found by testing
- Marginal CPU sensitivity (6/20 vs 0/20) is only a weak signal at 20 runs (power limit).
- Failure DNA can merge unrelated low-failure-rate tests (one low-confidence cluster on
  FlakeBench). Not tuned on the evaluation data; candidate fix needs new data.
- The CI capsule step was itself flaky while the fake service's random slowness was on;
  CI now runs it with `SLOW_PROBABILITY=0`.

### Decisions log
| Date | Decision | Reason |
|---|---|---|
| 11 Nov | No React/TypeScript before the expo | no npm in the build sandbox; zero-dependency dashboard works offline |
| 11 Nov | No FastAPI yet | CLI + static dashboard; no API needed |
| 11 Nov | Network isolation only | latency/loss needs NET_ADMIN and `tc` in every image |
| 11 Nov | No locale condition | PEP 538 locale coercion makes it nearly ineffective in slim images |
| 11 Nov | Standard library only at runtime | installs anywhere, offline at the expo |
| 11 Nov | Order capsules verify against the default order | for order failures, the order itself is the condition |
| 11 Nov | Do not retune DNA threshold on evaluation data | avoid overfitting the benchmark |
| 11 Nov | Results exported to workflow logs | artifact downloads are blocked in the build sandbox |
