"""The attack replay incidents ship with the app and run through the engine."""

from pipedelta.web.incidents import incident_list, load_incident
from pipedelta.web.service import analyze_file


def test_nine_incidents_listed_newest_first():
    items = incident_list()
    assert len(items) == 9
    dates = [c["date"] for c in items]
    assert dates == sorted(dates, reverse=True)
    for c in items:
        assert c["after"] and c["source"].startswith("https://")


def test_load_incident_rejects_bad_ids():
    assert load_incident("../../etc/passwd") is None
    assert load_incident("r99-nope") is None


def test_ghostaction_push_is_high():
    case = load_incident("r02-ghostaction-2026-direct-push")
    assert case is not None
    result = analyze_file(case["name"], case["before"], case["after"], "inventory")
    assert result["summary"]["level"] == "high"


def test_action_file_case_is_listed_but_not_runnable():
    tj = next(c for c in incident_list() if "tj-actions" in c["id"])
    assert tj["runnable"] is False
    assert load_incident(tj["id"]) is None
