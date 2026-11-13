"""Build docs/EVALUATION.md from the JSON results, so no number is typed by hand."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

R = Path(__file__).parent / "results"


def load(name: str):
    return json.loads((R / name).read_text())


def attack_line(rows):
    visible = [r for r in rows if r["visible"]]
    return (
        sum(r["blocked_at_default"] for r in rows),
        len(rows),
        sum(r["blocked_at_default"] for r in visible),
        len(visible),
    )


def history_total(rows):
    c: Counter[str] = Counter()
    for r in rows:
        c.update(r["levels"])
    return c, sum(c.values())


def main() -> None:
    a1, a2 = load("attacks-v0.1.json"), load("attacks-v0.2.json")
    h1, h2 = load("history-v0.1.json"), load("history-v0.2.json")
    b1, n, v1, nv = attack_line(a1)
    b2, _, v2, _ = attack_line(a2)
    t1, m1 = history_total(h1)
    t2, m2 = history_total(h2)
    reasons: Counter[str] = Counter()
    for r in h2:
        reasons.update(r["high_reasons"])
    unreadable = sum(r["unreadable"] for r in h2)
    commits = sum(r["workflow_commits"] for r in h2)

    out = []
    w = out.append
    w("# Evaluation\n")
    w("Every number on this page is produced by the scripts in `evaluation/` and copied")
    w("from `evaluation/results/*.json` by `evaluation/write_report.py`.\n")
    w("There are two separate tests. They answer different questions and their numbers")
    w("must not be combined.\n")
    w("## Summary\n")
    w("| | Version 0.1 | Version 0.2 |")
    w("|---|---|---|")
    w(f"| Attack cases blocked at the default gate | {b1} of {n} | {b2} of {n} |")
    w(f"| Same, counting only cases where a workflow file changes | {v1} of {nv} | {v2} of {nv} |")
    w(
        f"| Real past workflow commits blocked at the default gate | {t1['high']} of {m1} ({t1['high'] / m1:.1%}) | {t2['high']} of {m2} ({t2['high'] / m2:.1%}) |\n"
    )
    w("Version 0.2 was written **after** looking at the version 0.1 results. Two of its")
    w("rules (hidden decoded commands, and `toJSON(secrets)`) were added because cases 03")
    w("and 04 were missed. So the version 0.2 attack score is not independent evidence:")
    w("the tool was adjusted to those cases. The fair statement is that version 0.1,")
    w(f"written before any testing, blocked {v1} of {nv}.\n")
    w("## Test 1: reconstructed attack cases\n")
    w("Question: when a pipeline change follows a publicly described attack pattern, does")
    w("PipeDelta block it at the default setting (any high-level new power)?\n")
    w("The cases are in `evaluation/attacks/`. They are **reconstructions** written for")
    w("this project from public descriptions, with harmless placeholder addresses. They are")
    w("not the original malicious files, and twelve cases is a small set chosen by the")
    w("author of the tool. Each `case.json` names its source.\n")
    w("| Case | What it is | v0.1 | v0.2 |")
    w("|---|---|---|---|")
    for r1, r2 in zip(a1, a2, strict=True):

        def cell(r):
            if not r["visible"]:
                return "cannot see"
            return "blocked" if r["blocked_at_default"] else f"missed ({r['level']})"

        w(f"| {r1['case'][:2]} | {r1['title']} | {cell(r1)} | {cell(r2)} |")
    w("")
    w("What the misses mean:\n")
    w("- **Cases 06 and 08** cannot be seen at all. The attack happens without any change")
    w("  to the victim's workflow file. PipeDelta can only flag the earlier change that")
    w("  created the weakness (cases 05 and 07).")
    w("- **Case 10** is reported as medium, not blocked: the secret is seen but the")
    w("  address comes from a variable. This is the limit stated in the README.")
    w("- **Case 11** is missed: PipeDelta has no rule about what an artifact upload contains.\n")
    w("## Test 2: real workflow history of eight projects\n")
    w("Question: how often would PipeDelta have interrupted maintainers of real projects?\n")
    w("The script replayed every non-merge commit that touched `.github/workflows/` in")
    w(f"eight well-known Python projects ({commits} commits), comparing each commit with its")
    w(f"parent. Only git history was read; no project code was run. {unreadable} commits were")
    w("skipped because a workflow file was not valid YAML at that point.\n")
    w(
        "| Project | Commit studied up to | Workflow commits | No new power | Low | Medium | High (blocked) |"
    )
    w("|---|---|---|---|---|---|---|")
    for r in h2:
        lv = r["levels"]
        w(
            f"| {r['repo']} | `{r['head'][:10]}` | {r['workflow_commits']} | {lv.get('none', 0)} | {lv.get('low', 0)} | {lv.get('medium', 0)} | {lv.get('high', 0)} |"
        )
    w(f"| **Total** | | {commits} | {t2['none']} | {t2['low']} | {t2['medium']} | {t2['high']} |\n")
    w(f"At the default setting PipeDelta 0.2 would have blocked {t2['high']} of {m2} commits")
    w(
        f"({t2['high'] / m2:.1%}). Version 0.1 blocked {t1['high']} ({t1['high'] / m1:.1%}); most of the"
    )
    w("difference came from no longer treating a version bump of an action already in use,")
    w("or a renamed job, as a new power.\n")
    w("Why the blocked commits were blocked (counted per high-level finding, version 0.2):\n")
    w("| Reason | Findings |")
    w("|---|---|")
    for reason, count in reasons.most_common():
        w(f"| {reason} | {count} |")
    w("")
    w("How to read this:\n")
    w("- These commits are **not labelled**. Nobody has checked which of them were")
    w("  actually risky, so this is a block rate, not a false-alarm rate. None of them is")
    w("  a known attack.")
    w("- The largest reason is a new outside action referenced by a movable tag. Research")
    w("  papers call that a misconfiguration, so many of these blocks are arguably")
    w("  correct. They are still interruptions that maintainers of these projects did not ask for.")
    w("- About one workflow change in ten being blocked is probably too many for a")
    w("  required check on a busy project. A realistic use today is as a comment that")
    w("  informs the reviewer (`fail-on: never`), with blocking reserved for teams that")
    w("  already lock their actions to commits.\n")
    w("## What has not been done\n")
    w("- No comparison against existing scanners (zizmor, poutine) on the same cases.")
    w("- No test on original malicious workflow files.")
    w("- No manual labelling of the blocked commits.")
    w("- Only Python projects were studied.")
    w("- No measurement of whether the plain-language sentences help a human reviewer.\n")
    w("## Reproduce\n")
    w("    pip install -e .")
    w("    python evaluation/run_attacks.py evaluation/results/attacks-v0.2.json")
    w(
        "    git clone --no-checkout https://github.com/pallets/flask /tmp/hist/flask   # and the others"
    )
    w("    python evaluation/run_history.py evaluation/results/history-v0.2.json /tmp/hist/*")
    w("    python evaluation/write_report.py\n")
    w("The version 0.1 result files were produced by commit `6492d9f`.")
    Path("docs/EVALUATION.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
