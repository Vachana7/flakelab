# 🔬 FlakeLab report

**Target:** Docker image flakelab-demo:latest on network flakelab-net  
**Status:** complete, 10 runs per condition, significance level 0.05 with Holm-Bonferroni correction

| Tests | Flaky at baseline | Hidden sensitivities | Supported hypotheses | Unknown cause | Clusters |
|---|---|---|---|---|---|
| 13 | 2 | 6 | 7 | 1 | 2 |

## Failures per condition

| Test | Baseline | CPU 0.25 core | Memory 128 MB | Network off | Reverse order | Shuffled order | Timezone UTC+5:30 | Verdict |
|---|---|---|---|---|---|---|---|---|
| `test_session_tokens_unique` | 🟨 2/10 | 🟨 1/10 | 🟨 1/10 | 🟨 1/10 | 🟨 4/10 | 🟨 1/10 | 🟨 2/10 | ❓ Unknown cause |
| `test_export_catalog` | 🟩 0/10 | 🟩 0/10 | 🟥 10/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🔬 Memory sensitivity |
| `test_add_stock` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | ✅ Stable |
| `test_low_stock_alert` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟥 10/10 | 🟥 9/10 | 🟩 0/10 | 🔬 Test-order dependency (shared state) |
| `test_reserve_stock` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟥 10/10 | 🟨 4/10 | 🟩 0/10 | 🔬 Test-order dependency (shared state) |
| `test_authorize_within_sla` | 🟩 0/10 | 🟥 9/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🔬 Resource sensitivity (CPU / timing) |
| `test_refund_deducts_fee` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | ✅ Stable |
| `test_discount` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | ✅ Stable |
| `test_gst` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | ✅ Stable |
| `test_invalid_discount` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | ✅ Stable |
| `test_report_title` | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🟥 10/10 | 🔬 Environment assumption (timezone) |
| `test_delivery_forecast` | 🟩 0/10 | 🟩 0/10 | 🟨 1/10 | 🟥 10/10 | 🟩 0/10 | 🟩 0/10 | 🟩 0/10 | 🔬 Hidden external dependency |
| `test_weather_alerts` | 🟨 4/10 | 🟨 1/10 | 🟨 1/10 | 🟥 10/10 | 🟨 2/10 | 🟨 1/10 | 🟨 3/10 | 🔬 Hidden external dependency |

## Findings

### ❓ `tests/test_auth.py::test_session_tokens_unique`

**Unknown cause:** The test is unreliable, but none of the tested conditions explains its failures. Possible causes: internal randomness, concurrency inside the test, or a factor FlakeLab did not test.

### 🔬 `tests/test_exports.py::test_export_catalog`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 10/10 runs with Memory 128 MB vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Memory sensitivity. The test fails more often when memory is limited. It may allocate more memory than a small CI runner provides.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Use smaller test data, stream instead of loading everything into memory, or document the minimum runner memory.

**Reproduce** (fails 100% of runs under this condition, vs never at baseline).
```bash
docker run --rm --network flakelab-net --memory 128m --memory-swap 128m flakelab-demo:latest python -m pytest tests/test_exports.py::test_export_catalog
```

### 🔬 `tests/test_inventory.py::test_low_stock_alert`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 10/10 runs with Reverse order vs 0/10 at baseline (p < 0.001, significant after correction).
- Failed 9/10 runs with Shuffled order vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Test-order dependency (shared state). The test's result depends on which tests ran before it, so tests share state.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Reset shared state in fixtures, avoid module-level mutable data, and make every test create the data it needs.

**Reproduce** (fails 100% of runs under this condition, vs never at baseline). Runs the test on its own, without the earlier tests it depends on.
```bash
docker run --rm --network flakelab-net flakelab-demo:latest python -m pytest tests/test_inventory.py::test_low_stock_alert
```

### 🔬 `tests/test_inventory.py::test_reserve_stock`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 10/10 runs with Reverse order vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Test-order dependency (shared state). The test's result depends on which tests ran before it, so tests share state.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Reset shared state in fixtures, avoid module-level mutable data, and make every test create the data it needs.

**Reproduce** (fails 100% of runs under this condition, vs never at baseline). Runs the test on its own, without the earlier tests it depends on.
```bash
docker run --rm --network flakelab-net flakelab-demo:latest python -m pytest tests/test_inventory.py::test_reserve_stock
```

### 🔬 `tests/test_payments.py::test_authorize_within_sla`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 9/10 runs with CPU 0.25 core vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Resource sensitivity (CPU / timing). The test fails more often when CPU is scarce. It probably depends on something finishing within a fixed time.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Replace fixed sleeps and hard deadlines with condition-based waits, or mock the clock. If a deadline is a real requirement, test it separately on controlled hardware.

**Reproduce** (fails 90% of runs under this condition, vs never at baseline).
```bash
docker run --rm --network flakelab-net --cpus 0.25 flakelab-demo:latest python -m pytest tests/test_payments.py::test_authorize_within_sla
```

### 🔬 `tests/test_reports.py::test_report_title`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 10/10 runs with Timezone UTC+5:30 vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Environment assumption (timezone). The test fails when the machine's timezone changes, so it assumes a particular local time.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Use timezone-aware datetimes (UTC) in code, and pass time zones explicitly instead of relying on the machine's setting.

**Reproduce** (fails 100% of runs under this condition, vs never at baseline).
```bash
docker run --rm --network flakelab-net -e TZ=IST-5:30 flakelab-demo:latest python -m pytest tests/test_reports.py::test_report_title
```

### 🔬 `tests/test_weather.py::test_delivery_forecast`

> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns would not find this. It can break on a different CI runner.

**Confirmed observations**
- Failed 10/10 runs with Network off vs 0/10 at baseline (p < 0.001, significant after correction).

**Supported hypothesis:** Hidden external dependency. The test fails more often without network access, so it depends on a service outside the test.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Mock or fake the external service in unit tests, and move real network checks into a separate integration-test job.

**Reproduce** (fails 100% of runs under this condition, vs never at baseline).
```bash
docker run --rm --network none flakelab-demo:latest python -m pytest tests/test_weather.py::test_delivery_forecast
```

### 🔬 `tests/test_weather.py::test_weather_alerts`

**Confirmed observations**
- Failed 10/10 runs with Network off vs 4/10 at baseline (p = 0.005, significant after correction).

**Supported hypothesis:** Hidden external dependency. The test fails more often without network access, so it depends on a service outside the test.
_This is an association found by controlled experiments, not proof of the root cause._

**Suggested fix:** Mock or fake the external service in unit tests, and move real network checks into a separate integration-test job.

**Reproduce** (fails 100% of runs under this condition, vs about 1 in 2 runs at baseline).
```bash
docker run --rm --network none flakelab-demo:latest python -m pytest tests/test_weather.py::test_weather_alerts
```

## Failure DNA

Tests whose failure rates react to the same conditions. A shared signature suggests the same kind of weakness, not proof of one root cause.

- **DNA cluster 1** (2 tests, medium confidence): `test_delivery_forecast`, `test_weather_alerts`. Common significant conditions: Network off. All members react to Network off and usually fail in the same runs: likely one shared dependency or event.

## Co-failure groups

Tests that fail in the same runs probably share a cause. Fixing the shared cause can fix all of them.

- **Cluster 1** (2 tests, 74% co-failure similarity): `test_low_stock_alert`, `test_reserve_stock`. Shared signature: Test-order dependency (shared state).
- **Cluster 2** (2 tests, 50% co-failure similarity): `test_delivery_forecast`, `test_weather_alerts`. Shared signature: Hidden external dependency.

## Reproduction capsules

- `tests/test_auth.py::test_session_tokens_unique` → `capsules/tests_test_auth.py__test_session_tokens_unique`
- `tests/test_exports.py::test_export_catalog` → `capsules/tests_test_exports.py__test_export_catalog`
- `tests/test_inventory.py::test_low_stock_alert` → `capsules/tests_test_inventory.py__test_low_stock_alert`
- `tests/test_inventory.py::test_reserve_stock` → `capsules/tests_test_inventory.py__test_reserve_stock`
- `tests/test_payments.py::test_authorize_within_sla` → `capsules/tests_test_payments.py__test_authorize_within_sla`
- `tests/test_reports.py::test_report_title` → `capsules/tests_test_reports.py__test_report_title`
- `tests/test_weather.py::test_delivery_forecast` → `capsules/tests_test_weather.py__test_delivery_forecast`
- `tests/test_weather.py::test_weather_alerts` → `capsules/tests_test_weather.py__test_weather_alerts`

Verify one with `flakelab capsule verify <path>`.

## Evaluation against known causes

Diagnosis matched the planted cause for **13/13** tests. Of 8 problem tests, **2** ever failed in plain baseline reruns, while FlakeLab flagged **8**.

_Ground truth exists only for deliberately designed fixtures, so this checks the tool works as designed. It is not evidence of real-world accuracy._

<sub>FlakeLab reports associations between environment conditions and failures. Results depend on the number of runs and the machine used.</sub>
