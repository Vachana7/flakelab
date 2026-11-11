from pathlib import Path

from flakelab.conditions import get_conditions
from flakelab.experiment import Experiment
from flakelab.runners import DockerRunner, LocalRunner, _parse_plugin_output

MINI = Path(__file__).parent / "fixtures" / "mini_project"


def cond(name):
    return next(c for c in get_conditions(None) if c.name == name)


def test_local_runner_end_to_end(tmp_path):
    runner = LocalRunner(str(MINI), ["tests"])
    conditions = get_conditions(["reverse_order", "timezone_ist", "cpu_low"])
    exp = Experiment(runner, conditions, runs=4, out_dir=tmp_path, log=lambda *a: None)
    doc = exp.run()
    v = {t["name"]: t["verdict"] for t in doc["tests"]}
    assert v["test_needs_first"]["categories"] == ["order"]
    assert v["test_timezone"]["categories"] == ["timezone"]
    assert v["test_always_passes"]["level"] == "stable"
    # The local runner cannot limit CPU, so that condition is skipped, not faked.
    assert [c["name"] for c in doc["meta"]["skipped_conditions"]] == ["cpu_low"]


def test_crash_is_attributed_to_running_test():
    outcomes, crashed, note = _parse_plugin_output(
        {"outcomes": {"a": "passed"}, "running": "b", "finished": False}
    )
    assert crashed and outcomes == {"a": "passed", "b": "crashed"}
    assert "b" in note


def test_docker_create_args_apply_condition():
    r = DockerRunner("demo:latest", ["tests"], network="flakelab-net")
    args = r._create_args(cond("cpu_low"), 0, 42, "c1")
    assert args[args.index("--cpus") + 1] == "0.25"
    assert args[args.index("--network") + 1] == "flakelab-net"
    assert "TZ=UTC0" in args


def test_no_network_condition_overrides_project_network():
    r = DockerRunner("demo:latest", [], network="flakelab-net")
    args = r._create_args(cond("no_network"), 0, 42, "c1")
    assert args.count("--network") == 1
    assert args[args.index("--network") + 1] == "none"


def test_reproduce_command_is_runnable_text():
    r = DockerRunner("demo:latest", [], network="flakelab-net")
    cmd = r.reproduce_command(cond("timezone_ist"), "tests/test_reports.py::test_report_title")
    assert cmd.startswith("docker run --rm --network flakelab-net")
    assert "TZ=IST-5:30" in cmd and cmd.endswith("tests/test_reports.py::test_report_title")
