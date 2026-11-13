"""Run PipeDelta on every past commit that changed a workflow file in a repository.

Usage: python evaluation/run_history.py OUT.json REPO_DIR [REPO_DIR ...]
Only reads git history. Does not run any code from the repositories.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

from pipedelta.delta import compare, overall

WF = ".github/workflows/"


def git(repo: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=False, errors="replace"
    )


def show(repo: str, ref: str, path: str) -> str | None:
    result = git(repo, "show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else None


def study(repo: str) -> dict[str, object]:
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    commits = git(repo, "log", "--no-merges", "--format=%H", "--", WF).stdout.split()
    levels: Counter[str] = Counter()
    high_reasons: Counter[str] = Counter()
    unreadable = 0
    crashed = 0
    for commit in commits:
        parent = f"{commit}^"
        if git(repo, "rev-parse", "--verify", "-q", parent).returncode != 0:
            parent = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree
        listing = git(repo, "diff", "--name-status", "-M", "-z", parent, commit, "--", WF).stdout
        parts = [part for part in listing.split("\0") if part]
        pairs: list[tuple[str, str]] = []
        i = 0
        while i < len(parts):
            if parts[i].startswith("R") and i + 2 < len(parts):
                pairs.append((parts[i + 1], parts[i + 2]))
                i += 3
            elif parts[i].startswith("C") and i + 2 < len(parts):
                pairs.append((parts[i + 2], parts[i + 2]))
                i += 3
            elif i + 1 < len(parts):
                pairs.append((parts[i + 1], parts[i + 1]))
                i += 2
            else:
                break
        findings = []
        bad = False
        for old_path, path in pairs:
            if not path.endswith((".yml", ".yaml")):
                continue
            try:
                findings += compare(show(repo, parent, old_path), show(repo, commit, path))
            except yaml.YAMLError:
                bad = True
            except Exception:  # noqa: BLE001 - a bug in PipeDelta; count it honestly
                crashed += 1
                bad = True
        if bad:
            unreadable += 1
            continue
        level = overall(findings)
        levels[level] += 1
        if level == "high":
            for f in findings:
                if f.level == "high":
                    reason = f.power.kind
                    if reason == "action":
                        reason = "outside action not locked to a commit"
                    elif reason == "permission":
                        reason = "write permission"
                    elif reason == "trigger":
                        reason = f"trigger {f.power.name}"
                    elif reason in ("network", "secret"):
                        reason = "secret and new network address in the same job"
                    high_reasons[reason] += 1
    return {
        "repo": Path(repo).name,
        "head": head,
        "workflow_commits": len(commits),
        "unreadable": unreadable,
        "crashed": crashed,
        "levels": dict(levels),
        "high_reasons": dict(high_reasons),
    }


def main(out: str, repos: list[str]) -> None:
    rows = [study(r) for r in repos]
    Path(out).write_text(json.dumps(rows, indent=2) + "\n")
    total: Counter[str] = Counter()
    for r in rows:
        total.update(r["levels"])  # type: ignore[arg-type]
        print(
            r["repo"],
            r["workflow_commits"],
            r["levels"],
            "unreadable",
            r["unreadable"],
            "crashed",
            r["crashed"],
        )
    n = sum(total.values())
    print(
        "TOTAL",
        n,
        dict(total),
        f"blocked at default: {total['high']}/{n} = {total['high'] / n:.1%}",
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
