"""Checks that the Docker runner really applied each condition.

Used by CI after a short real-Docker experiment. It checks raw failure counts,
not statistical verdicts: with only 3 runs per condition no result can be
significant, and that is not what this test is about. It answers one question:
did --network none, --memory and --cpus actually change the environment?
"""

import json
import sys

FAIL = {"failed", "error", "crashed"}


def failures(doc: dict, test_suffix: str, condition: str) -> tuple[int, int]:
    runs = [r for r in doc["runs"] if r["condition"] == condition]
    fails = 0
    for r in runs:
        outcome = next((o for t, o in r["outcomes"].items() if t.endswith(test_suffix)), None)
        fails += outcome in FAIL
    return fails, len(runs)


def main(path: str) -> int:
    doc = json.load(open(path))
    problems = []
    if doc["meta"]["status"] != "done":
        problems.append("experiment did not finish")
    crashed = [r for r in doc["runs"] if r["crashed"]]
    if crashed:
        problems.append(f"{len(crashed)} runs crashed: {[r['note'] for r in crashed]}")

    checks = [
        # (test, condition, minimum failures out of 3, what it proves)
        ("test_delivery_forecast", "no_network", 3, "--network none cuts the network"),
        ("test_export_catalog", "memory_low", 3, "--memory limit kills the big export"),
        ("test_authorize_within_sla", "cpu_low", 2, "--cpus limit slows the fraud check"),
        ("test_discount", "cpu_low", 0, "stable tests still pass under limits"),
    ]
    for test, cond, minimum, meaning in checks:
        fails, runs = failures(doc, test, cond)
        ok = fails >= minimum if minimum else fails == 0
        print(f"{'PASS' if ok else 'FAIL'}  {test} under {cond}: {fails}/{runs}  ({meaning})")
        if not ok:
            problems.append(f"{test} under {cond}: {fails}/{runs}")
    base_fails, base_runs = failures(doc, "test_export_catalog", "baseline")
    print(f"info  test_export_catalog at baseline: {base_fails}/{base_runs}")

    if problems:
        print("\nIntegration check failed:\n- " + "\n- ".join(problems))
        return 1
    print("\nAll Docker conditions were applied correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
