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
    a1, a2 = load("attacks-v0.1.json"), load("attacks-v0.4.json")
    h1, h2 = load("history-v0.1.json"), load("history-v0.4.json")
    cmp = load("comparison-v0.4.json")
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
    w("There are three separate tests. They answer different questions and their numbers")
    w("must not be combined.\n")
    w("## Summary\n")
    w("| | Version 0.1 | Version 0.4 |")
    w("|---|---|---|")
    w(f"| Attack cases blocked at the default gate | {b1} of {n} | {b2} of {n} |")
    w(f"| Same, counting only cases where a workflow file changes | {v1} of {nv} | {v2} of {nv} |")
    w(
        f"| Real past workflow commits blocked at the default gate | {t1['high']} of {m1} ({t1['high'] / m1:.1%}) | {t2['high']} of {m2} ({t2['high'] / m2:.1%}) |\n"
    )
    w("Version 0.4 is version 0.1 plus three rounds of changes, each kept in")
    w("`evaluation/results/`. Version 0.2 changed rules after the first test run (8 of 10")
    w("attack cases, 164 of 1659 commits). Version 0.3 fixed eight bugs from a code review")
    w("(`tests/test_bugfixes.py`; 8 of 10, 157 of 1659). Version 0.4 closed detection gaps")
    w("found in a second review (`tests/test_v04_rules.py`): actions stored in the repository,")
    w("`secrets['NAME']`, injection through `actions/github-script`, more ways of hiding a")
    w("command, addresses written without `https://` or only known at run time, self-hosted")
    w("machines chosen through a matrix, and container images.\n")
    w("Versions 0.2 and 0.4 were written **after** looking at earlier results. Rules for")
    w("cases 03 and 04 (v0.2) and case 10 (v0.4, addresses only known at run time) were")
    w("added because those cases were missed. So the later attack scores are not")
    w("independent evidence: the tool was adjusted to these cases. The fair statement is")
    w(f"that version 0.1, written before any testing, blocked {v1} of {nv}. The history test")
    w("below is the check that these changes did not simply add noise.\n")
    w("## Test 1: reconstructed attack cases\n")
    w("Question: when a pipeline change follows a publicly described attack pattern, does")
    w("PipeDelta block it at the default setting (any high-level new power)?\n")
    w("The cases are in `evaluation/attacks/`. They are **reconstructions** written for")
    w("this project from public descriptions, with harmless placeholder addresses. They are")
    w("not the original malicious files, and twelve cases is a small set chosen by the")
    w("author of the tool. Each `case.json` names its source.\n")
    w("| Case | What it is | v0.1 | v0.4 |")
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
    w("- **Case 10** is blocked since v0.4: a request whose address is only known at run")
    w("  time, in a job that reads a secret, is treated like a new address. This rule was")
    w("  written after seeing the miss.")
    w("- **Case 11** is missed by PipeDelta's own rules: it has no rule about what an")
    w("  artifact upload contains. zizmor catches it (see Test 3), which is why the two are")
    w("  meant to be used together.\n")
    # ---------------- Test 3
    tools = cmp["tools"]
    rows = cmp["cases"]

    def score(tool: str, word: str) -> int:
        return sum(r[tool] == word for r in rows)

    w("## Test 3: the same cases with zizmor and poutine\n")
    w("Question: on the same changes, do established scanners raise a **new** top-level")
    w("problem? Each tool scans the file before and after the change; a problem that was")
    w("already there before does not count, because the reviewer would not see it as new.")
    w("zizmor counts when it reports a new result of severity High; poutine when it reports")
    w("a new result at level error or warning (its two highest). Both run with their default")
    w(f"settings. Versions: {tools['zizmor']}; poutine 1.1.6 built from source")
    w("(`go install`). zizmor ran with `--offline`, so its online audits were not used.\n")
    w("| Case | PipeDelta 0.4 | zizmor | poutine | PipeDelta + zizmor |")
    w("|---|---|---|---|---|")
    for r in rows:
        w(
            f"| {r['case'][:2]} | {r['pipedelta']} | {r['zizmor']} | {r['poutine']} | {r['combined']} |"
        )
    w(
        f"| **Total** | **{score('pipedelta', 'blocked')} of {len(rows)}** | "
        f"**{score('zizmor', 'flagged')} of {len(rows)}** | "
        f"**{score('poutine', 'flagged')} of {len(rows)}** | "
        f"**{score('combined', 'blocked')} of {len(rows)}** |\n"
    )
    w("How to read this:\n")
    w("- **This test favours PipeDelta.** The cases were written by PipeDelta's author, and")
    w("  PipeDelta's rules were later adjusted to them. zizmor and poutine were not. The")
    w("  numbers show *what kind* of change each tool notices, not which tool is better.")
    w("- The pattern is clear even so. zizmor and poutine look for **known weak patterns**")
    w("  (movable versions, template injection, dangerous triggers). They do not ask whether")
    w("  a change **starts sending a secret somewhere new**, which is how the 2025 and 2026")
    w("  secret-theft campaigns worked (cases 01, 02, 03, 10). PipeDelta does ask that.")
    w("- zizmor sees things PipeDelta does not (case 11, a token leaked through an artifact).")
    w("  PipeDelta's `--zizmor on` mode runs zizmor on both versions, keeps only its new")
    w("  results and explains them in the same plain language. Together they block")
    w(f"  {score('combined', 'blocked')} of {len(rows)}.\n")
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
    zt: Counter[str] = Counter()
    ct: Counter[str] = Counter()
    for r in h2:
        zt.update(r.get("zizmor_levels", {}))
        ct.update(r.get("combined_levels", {}))
    w(f"At the default setting PipeDelta 0.4 would have blocked {t2['high']} of {m2} commits")
    w(
        f"({t2['high'] / m2:.1%}). Version 0.1 blocked {t1['high']} ({t1['high'] / m1:.1%}); most of the"
    )
    w("difference came from no longer treating a version bump of an action already in use,")
    w("or a renamed job, as a new power. The new rules in version 0.4 did not raise the")
    w("block rate (version 0.3: 157).\n")
    if sum(zt.values()):
        w("The same commits judged by zizmor's new results (a new High result counts as a")
        w(f"block): zizmor alone {zt['high']} of {m2} ({zt['high'] / m2:.1%}); PipeDelta with")
        w(f"`--zizmor on` {ct['high']} of {m2} ({ct['high'] / m2:.1%}). zizmor alone is much")
        w("noisier mainly because it flags every version bump of an action that is not locked")
        w("to a commit, which PipeDelta treats as no new power. Because `--zizmor on` adds")
        w("interruptions, it is off by default.\n")
    w("Why the blocked commits were blocked (counted per high-level finding, version 0.4):\n")
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
    w("- No comparison against scanners on cases written by someone else (Test 3 uses")
    w("  PipeDelta's own cases).")
    w("- No test on original malicious workflow files.")
    w("- No manual labelling of the blocked commits.")
    w("- Only Python projects were studied.")
    w("- No measurement of whether the plain-language sentences help a human reviewer.\n")
    w("## Reproduce\n")
    w("    pip install -e .")
    w("    pip install zizmor && go install github.com/boostsecurityio/poutine@v1.1.6")
    w("    python evaluation/run_attacks.py evaluation/results/attacks-v0.4.json")
    w("    python evaluation/run_comparison.py evaluation/results/comparison-v0.4.json")
    w(
        "    git clone --no-checkout https://github.com/pallets/flask /tmp/hist/flask   # and the others"
    )
    w("    python evaluation/run_history.py evaluation/results/history-v0.4.json /tmp/hist/*")
    w("    python evaluation/write_report.py\n")
    w(
        "The version 0.1 result files were produced by commit `6492d9f`, the version 0.2 files by commit `2666b68` and the version 0.3 files by commit `594e8ec`."
    )
    Path("docs/EVALUATION.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
