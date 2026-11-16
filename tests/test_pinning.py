"""How a change to an action's version reference is classified. Written first."""

from pipedelta.delta import compare, overall

SHA_A = "a" * 40
SHA_B = "b" * 40


def wf(ref: str) -> str:
    return (
        "on: push\npermissions:\n  contents: read\njobs:\n  build:\n    runs-on: x\n"
        f"    steps:\n      - uses: someone/tool@{ref}\n"
    )


def action_findings(old, new):
    return [f for f in compare(old, new) if f.power.kind == "action"]


def test_unpinned_to_pinned_is_an_improvement_and_does_not_count():
    found = action_findings(wf("v1"), wf(SHA_A))
    assert len(found) == 1
    assert found[0].change == "improved"
    assert overall(found) == "none"


def test_pinned_to_unpinned_is_a_high_regression():
    found = action_findings(wf(SHA_A), wf("v2"))
    assert len(found) == 1
    assert found[0].change == "gained"
    assert found[0].level == "high"


def test_pinned_commit_to_another_pinned_commit_is_a_changed_reference_not_an_improvement():
    found = action_findings(wf(SHA_A), wf(SHA_B))
    assert len(found) == 1
    assert found[0].change == "gained"
    assert found[0].level == "low"
    assert "different commit" in found[0].message


def test_unpinned_version_to_another_unpinned_version_is_a_version_change():
    found = action_findings(wf("v1"), wf("v2"))
    assert len(found) == 1
    assert found[0].change == "gained"
    assert found[0].level == "low"
    assert "version" in found[0].message


def test_removed_action_is_a_reduction():
    old = wf("v1")
    new = old.replace("      - uses: someone/tool@v1\n", "      - run: make\n")
    found = action_findings(old, new)
    assert len(found) == 1
    assert found[0].change == "reduced"


def test_brand_new_unpinned_action_is_still_high():
    old = wf("v1").replace("      - uses: someone/tool@v1\n", "      - run: make\n")
    assert overall(action_findings(old, wf("v1"))) == "high"


def test_pinning_passes_the_gate_and_is_labelled_in_the_report():
    from pipedelta.report import render_markdown, render_text

    results = {"ci.yml": compare(wf("v1"), wf(SHA_A))}
    assert "[IMPROVED" in render_text(results)
    assert "| improved |" in render_markdown(results)
    assert "no new powers" in render_markdown(results)
