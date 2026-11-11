"""Markdown report: used as the GitHub Actions job summary and PR comment."""

from __future__ import annotations

LEVEL_ICON = {
    "supported_hypothesis": "🔬",
    "weak_signal": "🟡",
    "unknown": "❓",
    "always_failing": "🛑",
    "stable": "✅",
}


def _cell(c: dict | None) -> str:
    if not c or not c["runs"]:
        return "—"
    rate = c["failures"] / c["runs"]
    dot = "🟩" if rate == 0 else ("🟨" if rate < 0.5 else "🟥")
    return f"{dot} {c['failures']}/{c['runs']}"


def _header(doc: dict) -> list[str]:
    meta, s = doc["meta"], doc["summary"]
    if meta["status"] == "done":
        status = "complete"
    else:
        status = f"running ({meta['completed_runs']}/{meta['total_runs']} runs)"
    return [
        "# 🔬 FlakeLab report",
        "",
        f"**Target:** {meta['target']}  ",
        (
            f"**Status:** {status}, {meta['runs_per_condition']} runs per condition, "
            f"significance level {meta['alpha']} with Holm-Bonferroni correction"
        ),
        "",
        (
            "| Tests | Flaky at baseline | Hidden sensitivities | Supported hypotheses "
            "| Unknown cause | Clusters |"
        ),
        "|---|---|---|---|---|---|",
        (
            f"| {s['tests']} | {s['baseline_flaky']} | {s['hidden_sensitivities']} | "
            f"{s['supported_hypotheses']} | {s['unknown']} | {s['clusters']} |"
        ),
        "",
    ]


def _matrix(doc: dict) -> list[str]:
    conds = doc["meta"]["conditions"]
    lines = [
        "## Failures per condition",
        "",
        "| Test | " + " | ".join(c["label"] for c in conds) + " | Verdict |",
        "|---|" + "---|" * len(conds) + "---|",
    ]
    for t in doc["tests"]:
        cells = " | ".join(_cell(t["per_condition"].get(c["name"])) for c in conds)
        v = t["verdict"]
        lines.append(f"| `{t['name']}` | {cells} | {LEVEL_ICON[v['level']]} {v['title']} |")
    lines.append("")
    return lines


def _finding(t: dict) -> list[str]:
    v = t["verdict"]
    lines = [f"### {LEVEL_ICON[v['level']]} `{t['nodeid']}`", ""]
    if t["hidden_sensitivity"]:
        lines += [
            (
                "> ⚠️ **Hidden sensitivity:** never failed at baseline, so plain reruns "
                "would not find this. It can break on a different CI runner."
            ),
            "",
        ]
    sig = [o for o in t["observations"] if o["significant"]]
    if sig:
        lines.append("**Confirmed observations**")
        lines += [f"- {o['text']}" for o in sig]
        lines.append("")
    if v["level"] == "supported_hypothesis":
        lines += [
            f"**Supported hypothesis:** {v['title']}. {v['explanation']}",
            (
                "_This is an association found by controlled experiments, not proof of "
                "the root cause._"
            ),
            "",
        ]
    else:
        lines += [f"**{v['title']}:** {v['explanation']}", ""]
    if v.get("fix"):
        lines += [f"**Suggested fix:** {v['fix']}", ""]
    r = t.get("reproduce")
    if r and r.get("command"):
        base = r["baseline_runs_to_failure"]
        base_txt = f"about 1 in {base:.0f} runs at baseline" if base else "never at baseline"
        note = f" {r['note']}" if r.get("note") else ""
        lines += [
            (
                f"**Reproduce** (fails {r['failure_rate']:.0%} of runs under this condition, "
                f"vs {base_txt}).{note}"
            ),
            "```bash",
            r["command"],
            "```",
            "",
        ]
    return lines


def _clusters(doc: dict) -> list[str]:
    if not doc.get("clusters"):
        return []
    lines = [
        "## Failure clusters",
        "",
        (
            "Tests that fail in the same runs probably share a cause. "
            "Fixing the shared cause can fix all of them."
        ),
        "",
    ]
    for c in doc["clusters"]:
        names = ", ".join(f"`{n.split('::')[-1]}`" for n in c["tests"])
        lines.append(
            f"- **Cluster {c['id']}** ({c['size']} tests, {c['similarity']:.0%} co-failure "
            f"similarity): {names}. Shared signature: {c['shared_title']}."
        )
    lines.append("")
    return lines


def _evaluation(doc: dict) -> list[str]:
    ev = doc.get("evaluation")
    if not ev or not ev["scored"]:
        return []
    return [
        "## Evaluation against known causes",
        "",
        (
            f"Diagnosis matched the planted cause for **{ev['correct']}/{ev['scored']}** "
            f"tests. Of {ev['problem_tests']} problem tests, "
            f"**{ev['visible_to_baseline_reruns']}** ever failed in plain baseline reruns, "
            f"while FlakeLab flagged **{ev['found_by_flakelab']}**."
        ),
        "",
        (
            "_Ground truth exists only for deliberately designed fixtures, so this checks "
            "the tool works as designed. It is not evidence of real-world accuracy._"
        ),
        "",
    ]


def render_markdown(doc: dict) -> str:
    lines = _header(doc) + _matrix(doc)
    problems = [t for t in doc["tests"] if t["verdict"]["level"] != "stable"]
    if problems:
        lines += ["## Findings", ""]
        for t in problems:
            lines += _finding(t)
    lines += _clusters(doc) + _evaluation(doc)
    skipped = doc["meta"].get("skipped_conditions")
    if skipped:
        names = ", ".join(f"{s['label']} ({s['reason']})" for s in skipped)
        lines += [f"_Skipped conditions: {names}._", ""]
    lines.append(
        "<sub>FlakeLab reports associations between environment conditions and failures. "
        "Results depend on the number of runs and the machine used.</sub>"
    )
    return "\n".join(lines) + "\n"
