"""Command line: pipedelta diff OLD NEW   |   pipedelta git BASE HEAD"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from .delta import Finding, compare, overall

WORKFLOW_DIR = ".github/workflows/"


def _read(path: str) -> str | None:
    if path in ("-", "/dev/null"):
        return None
    return Path(path).read_text(encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def render(results: dict[str, list[Finding]]) -> str:
    lines: list[str] = []
    everything = [f for fs in results.values() for f in fs]
    if not everything:
        return "PipeDelta: no new pipeline powers in this change.\n"
    lines.append(
        f"PipeDelta: this change gives the pipeline {len(everything)} new power(s). "
        f"Highest level: {overall(everything)}.\n"
    )
    for path, findings in results.items():
        if not findings:
            continue
        lines.append(path)
        for f in findings:
            lines.append(f"  [{f.level.upper():6}] {f.message}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipedelta")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diff", help="compare two workflow files")
    d.add_argument("old", help="old file, or - if it did not exist")
    d.add_argument("new", help="new file, or - if it was deleted")

    g = sub.add_parser("git", help="compare workflow files between two git commits")
    g.add_argument("base")
    g.add_argument("head")

    for p in (d, g):
        p.add_argument(
            "--fail-on",
            choices=["low", "medium", "high", "never"],
            default="high",
            help="exit with an error if a finding is at or above this level",
        )

    args = parser.parse_args(argv)
    results: dict[str, list[Finding]] = {}

    try:
        if args.command == "diff":
            results[args.new if args.new != "-" else args.old] = compare(
                _read(args.old), _read(args.new)
            )
        else:
            changed = _git("diff", "--name-only", args.base, args.head, "--", WORKFLOW_DIR)
            for path in changed.splitlines():
                if path.endswith((".yml", ".yaml")):
                    results[path] = compare(_git_show(args.base, path), _git_show(args.head, path))
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"pipedelta: {error}", file=sys.stderr)
        return 2
    except yaml.YAMLError as error:
        print(f"pipedelta: could not read a workflow file: {error}", file=sys.stderr)
        return 2

    print(render(results))

    if args.fail_on == "never":
        return 0
    order = ["low", "medium", "high"]
    worst = overall([f for fs in results.values() for f in fs])
    if worst != "none" and order.index(worst) >= order.index(args.fail_on):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
