"""pytest plugin that FlakeLab injects into every test run.

It does two jobs:
1. Reorders tests when FLAKELAB_ORDER is "reverse" or "random:<seed>".
2. Records each test's outcome to a JSON file (FLAKELAB_OUT) after EVERY test,
   so if the process is killed mid-run (for example by the out-of-memory killer)
   FlakeLab still knows which tests finished and which test was running.

This file deliberately uses only the Python standard library, because it runs
inside the project's own container where FlakeLab is not installed.
"""

import json
import os
import random

_OUT = os.environ.get("FLAKELAB_OUT", "/tmp/flakelab_out.json")
_state: dict = {
    "order": os.environ.get("FLAKELAB_ORDER", "default"),
    "collected": [],
    "outcomes": {},
    "running": None,
    "finished": False,
}


def _write():
    tmp = _OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(_state, fh)
    os.replace(tmp, _OUT)  # atomic, so a crash never leaves half a file


def pytest_collection_modifyitems(session, config, items):
    order = _state["order"]
    if order == "reverse":
        items.reverse()
    elif order.startswith("random:"):
        seed = int(order.split(":", 1)[1])
        random.Random(seed).shuffle(items)
    _state["collected"] = [item.nodeid for item in items]
    _write()


def pytest_runtest_logstart(nodeid, location):
    _state["running"] = nodeid
    _write()


def pytest_runtest_logreport(report):
    current = _state["outcomes"].get(report.nodeid)
    if report.when == "setup":
        if report.failed:
            _state["outcomes"][report.nodeid] = "error"
        elif report.skipped:
            _state["outcomes"][report.nodeid] = "skipped"
    elif report.when == "call":
        if report.passed:
            _state["outcomes"][report.nodeid] = "passed"
        elif report.skipped:
            _state["outcomes"][report.nodeid] = "skipped"
        else:
            _state["outcomes"][report.nodeid] = "failed"
    elif report.when == "teardown" and report.failed and current == "passed":
        _state["outcomes"][report.nodeid] = "error"


def pytest_runtest_logfinish(nodeid, location):
    _state["running"] = None
    _write()


def pytest_sessionfinish(session, exitstatus):
    _state["finished"] = True
    _write()
