import json

from fakes import SimulatedRunner

from flakelab.conditions import ALL_CONDITIONS, get_conditions
from flakelab.experiment import Experiment, build_schedule

EXPECTED = {
    "tests/test_payments.py::test_authorize_within_sla": "cpu",
    "tests/test_payments.py::test_refund_deducts_fee": "stable",
    "tests/test_weather.py::test_delivery_forecast": "network",
    "tests/test_weather.py::test_weather_alerts": "network",
    "tests/test_inventory.py::test_add_stock": "stable",
    "tests/test_inventory.py::test_reserve_stock": "order",
    "tests/test_inventory.py::test_low_stock_alert": "order",
    "tests/test_reports.py::test_report_title": "timezone",
    "tests/test_exports.py::test_export_catalog": "memory",
    "tests/test_auth.py::test_session_tokens_unique": "intrinsic",
    "tests/test_pricing.py::test_discount": "stable",
    "tests/test_pricing.py::test_gst": "stable",
    "tests/test_pricing.py::test_invalid_discount": "stable",
}


def run_simulation(tmp_path, runs=10):
    exp = Experiment(
        SimulatedRunner(),
        ALL_CONDITIONS,
        runs=runs,
        out_dir=tmp_path,
        expected=EXPECTED,
        log=lambda *a: None,
    )
    return exp.run()


def by_name(doc, name):
    return next(t for t in doc["tests"] if t["name"] == name)


def test_planted_causes_are_identified(tmp_path):
    doc = run_simulation(tmp_path)
    cats = {t["nodeid"]: t["verdict"]["categories"] for t in doc["tests"]}
    assert cats["tests/test_payments.py::test_authorize_within_sla"] == ["cpu"]
    assert cats["tests/test_exports.py::test_export_catalog"] == ["memory"]
    assert cats["tests/test_weather.py::test_delivery_forecast"] == ["network"]
    assert cats["tests/test_reports.py::test_report_title"] == ["timezone"]
    assert "order" in cats["tests/test_inventory.py::test_reserve_stock"]


def test_random_test_is_unknown_not_blamed_on_a_condition(tmp_path):
    doc = run_simulation(tmp_path)
    assert by_name(doc, "test_session_tokens_unique")["verdict"]["level"] == "unknown"


def test_stable_tests_stay_stable(tmp_path):
    doc = run_simulation(tmp_path)
    for name in ("test_discount", "test_gst", "test_refund_deducts_fee"):
        assert by_name(doc, name)["verdict"]["level"] == "stable"


def test_hidden_sensitivity_flag(tmp_path):
    doc = run_simulation(tmp_path)
    assert by_name(doc, "test_report_title")["hidden_sensitivity"] is True
    # Weather tests already fail sometimes at baseline, so not "hidden".
    assert by_name(doc, "test_delivery_forecast")["hidden_sensitivity"] is False


def test_weather_tests_form_a_cluster(tmp_path):
    doc = run_simulation(tmp_path)
    members = [set(c["tests"]) for c in doc["clusters"]]
    assert {
        "tests/test_weather.py::test_delivery_forecast",
        "tests/test_weather.py::test_weather_alerts",
    } in members


def test_evaluation_and_outputs(tmp_path):
    doc = run_simulation(tmp_path)
    ev = doc["evaluation"]
    assert ev["correct"] == ev["scored"] == len(EXPECTED)
    assert ev["visible_to_baseline_reruns"] < ev["found_by_flakelab"]
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved["meta"]["status"] == "done"
    assert saved["meta"]["completed_runs"] == len(ALL_CONDITIONS) * 10
    report = (tmp_path / "report.md").read_text()
    assert "FlakeLab report" in report and "test_report_title" in report
    assert (tmp_path / "index.html").exists()


def test_schedule_is_interleaved():
    sched = build_schedule(ALL_CONDITIONS, 2, SimulatedRunner())
    names = [c.name for c, _ in sched]
    assert names[: len(ALL_CONDITIONS)] == [c.name for c in ALL_CONDITIONS]
    assert len(sched) == 2 * len(ALL_CONDITIONS)


def test_get_conditions_always_includes_baseline():
    names = [c.name for c in get_conditions(["cpu_low"])]
    assert names == ["baseline", "cpu_low"]
