import json
from pathlib import Path

from fakes import SimulatedRunner

from flakelab.capsule import build_capsule, create_capsules, verify_capsule
from flakelab.conditions import ALL_CONDITIONS, get_conditions
from flakelab.experiment import Experiment
from flakelab.runners import LocalRunner

MINI = Path(__file__).parent / "fixtures" / "mini_project"


def simulated_doc(tmp_path):
    exp = Experiment(
        SimulatedRunner(), ALL_CONDITIONS, runs=10, out_dir=tmp_path, log=lambda *a: None
    )
    return exp.run()


def test_capsules_written_for_investigated_failures_only(tmp_path):
    doc = simulated_doc(tmp_path)
    names = {c["test"].split("::")[-1] for c in doc["meta"]["capsules"]}
    assert "test_report_title" in names and "test_export_catalog" in names
    assert "test_discount" not in names  # stable tests get no capsule
    for entry in doc["meta"]["capsules"]:
        folder = tmp_path / entry["path"]
        for f in ("capsule.json", "order.txt", "reproduce.sh", "reproduce.ps1", "README.md"):
            assert (folder / f).exists(), f
        assert (folder / "plugin" / "flakelab_pytest_plugin.py").exists()


def test_capsule_records_condition_and_order_prefix(tmp_path):
    doc = simulated_doc(tmp_path)
    test = next(t for t in doc["tests"] if t["name"] == "test_reserve_stock")
    capsule = build_capsule(doc, test)
    assert capsule["condition"]["category"] == "order"
    tests = capsule["execution"]["tests"]
    assert tests[-1] == test["nodeid"]  # the prefix ends with the failing test
    assert "FLAKELAB_ORDER" not in capsule["condition"]["env"]
    cpu = build_capsule(
        doc, next(t for t in doc["tests"] if t["name"] == "test_authorize_within_sla")
    )
    assert cpu["condition"]["cpu_limit"] == "0.25"
    assert cpu["experiment"]["condition_failures"] >= 6


def test_local_capsule_reproduces_order_and_timezone(tmp_path):
    runner = LocalRunner(str(MINI), ["tests"])
    exp = Experiment(
        runner,
        get_conditions(["reverse_order", "timezone_ist"]),
        runs=4,
        out_dir=tmp_path,
        log=lambda *a: None,
    )
    doc = exp.run()
    by_test = {e["test"].split("::")[-1]: tmp_path / e["path"] for e in doc["meta"]["capsules"]}
    assert set(by_test) == {"test_needs_first", "test_timezone"}

    import os

    cwd = os.getcwd()
    os.chdir(MINI)  # local capsules run from the project folder
    try:
        order = verify_capsule(by_test["test_needs_first"], runs=3, log=lambda *a: None)
        tz = verify_capsule(by_test["test_timezone"], runs=3, log=lambda *a: None)
    finally:
        os.chdir(cwd)
    assert order["verdict"] == "partially_reproduced" or order["verdict"] == "reproduced"
    assert (order["condition_failures"], order["baseline_failures"]) == (3, 0)
    assert (tz["condition_failures"], tz["baseline_failures"]) == (3, 0)
    saved = json.loads((by_test["test_timezone"] / "verification.json").read_text())
    assert saved["runs_per_arm"] == 3


def test_create_capsules_from_results_file(tmp_path):
    doc = simulated_doc(tmp_path)
    folders = create_capsules(doc, tmp_path / "again")
    assert len(folders) == len(doc["meta"]["capsules"])
