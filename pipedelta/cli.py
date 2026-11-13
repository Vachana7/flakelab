"""Command line: pipedelta diff OLD NEW   |   pipedelta git BASE HEAD"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from .delta import Finding, compare, overall
from .github import upsert_comment
from .report import all_findings, render_markdown, render_text

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


def compare_commits(base: str, head: str) -> dict[str, list[Finding]]:
    results: dict[str, list[Finding]] = {}
    changed = _git("diff", "--name-only", base, head, "--", WORKFLOW_DIR)
    for path in changed.splitlines():
        if path.endswith((".yml", ".yaml")):
            results[path] = compare(_git_show(base, path), _git_show(head, path))
    return results


def _exit_code(results: dict[str, list[Finding]], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    order = ["low", "medium", "high"]
    worst = overall(all_findings(results))
    if worst != "none" and order.index(worst) >= order.index(fail_on):
        return 1
    return 0


def _append(path: str | None, text: str) -> None:
    """Add text to a file GitHub gave us. A failure here must not hide the result."""
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        print(f"pipedelta: could not write {path}: {error}", file=sys.stderr)


def _run_action(fail_on: str) -> int:
    """Entry point when PipeDelta runs as a GitHub Action on a pull request."""
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        event = json.load(handle)
    pr = event.get("pull_request")
    if not pr:
        print("pipedelta: this event is not a pull request, nothing to compare.")
        return 0

    results = compare_commits(pr["base"]["sha"], pr["head"]["sha"])
    print(render_text(results))
    markdown = render_markdown(results)

    token = os.environ.get("PIPEDELTA_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if token and repo and results:
        print("pull request comment:", upsert_comment(repo, int(pr["number"]), token, markdown))

    level = overall(all_findings(results))
    _append(os.environ.get("GITHUB_STEP_SUMMARY"), markdown)
    _append(os.environ.get("GITHUB_OUTPUT"), f"level={level}\ncount={len(all_findings(results))}\n")
    return _exit_code(results, fail_on)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipedelta")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diff", help="compare two workflow files")
    d.add_argument("old", help="old file, or - if it did not exist")
    d.add_argument("new", help="new file, or - if it was deleted")

    g = sub.add_parser("git", help="compare workflow files between two git commits")
    g.add_argument("base")
    g.add_argument("head")

    a = sub.add_parser("action", help="run inside GitHub Actions on a pull request")

    for p in (d, g, a):
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
        elif args.command == "action":
            return _run_action(args.fail_on)
        else:
            results = compare_commits(args.base, args.head)
    except (OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"pipedelta: {error}", file=sys.stderr)
        return 2
    except yaml.YAMLError as error:
        print(f"pipedelta: could not read a workflow file: {error}", file=sys.stderr)
        return 2

    print(render_text(results))
    return _exit_code(results, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
