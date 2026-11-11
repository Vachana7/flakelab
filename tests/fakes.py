"""A simulated runner, used ONLY by the unit tests.

It produces outcomes from fixed failure probabilities so the analysis code can
be tested quickly and deterministically without Docker. It is intentionally
not available from the command line: real results must come from real runs.
"""

import random

from flakelab.runners import RunResult

# Failure probability per test and condition, mirroring the demo's planted causes.
DEMO_PROFILE = {
    "tests/test_payments.py::test_authorize_within_sla": {"baseline": 0.0, "cpu_low": 1.0},
    "tests/test_payments.py::test_refund_deducts_fee": {},
    "tests/test_weather.py::test_delivery_forecast": {"baseline": 0.1, "no_network": 1.0},
    "tests/test_weather.py::test_weather_alerts": {"baseline": 0.1, "no_network": 1.0},
    "tests/test_inventory.py::test_add_stock": {},
    "tests/test_inventory.py::test_reserve_stock": {"reverse_order": 1.0, "shuffled_order": 0.5},
    "tests/test_inventory.py::test_low_stock_alert": {"reverse_order": 1.0, "shuffled_order": 0.6},
    "tests/test_reports.py::test_report_title": {"timezone_ist": 1.0},
    "tests/test_exports.py::test_export_catalog": {"memory_low": 1.0},
    "tests/test_auth.py::test_session_tokens_unique": {"*": 0.17},
    "tests/test_pricing.py::test_discount": {},
    "tests/test_pricing.py::test_gst": {},
    "tests/test_pricing.py::test_invalid_discount": {},
}


class SimulatedRunner:
    name = "simulated"

    def __init__(self, profile=None, seed=7):
        self.profile = profile or DEMO_PROFILE
        self.rng = random.Random(seed)

    def supports(self, condition):
        return True

    def describe(self):
        return "simulated runner (unit tests only)"

    def reproduce_command(self, condition, nodeid):
        return f"simulate --condition {condition.name} {nodeid}"

    def environment(self):
        return {"runner": "simulated", "project": {"python": "3.12.0"}, "network": None}

    def run(self, condition, index, seed):
        outcomes = {}
        # Correlated network failures: one slow-service event hits both weather tests.
        shared_draw = self.rng.random()
        for nodeid, probs in self.profile.items():
            p = probs.get(condition.name, probs.get("*", probs.get("baseline", 0.0)))
            if "test_weather" in nodeid and condition.name != "no_network":
                failed = shared_draw < p
            else:
                failed = self.rng.random() < p
            outcomes[nodeid] = "failed" if failed else "passed"
        order = list(self.profile)
        if condition.name == "reverse_order":
            order.reverse()
        return RunResult(
            condition.name,
            index,
            outcomes=outcomes,
            order=order,
            order_env=condition.full_env(index, seed)["FLAKELAB_ORDER"],
            duration=0.01,
            pytest_seconds=0.005,
        )
