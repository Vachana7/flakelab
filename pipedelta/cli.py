"""Command line: pipedelta diff OLD NEW   |   pipedelta git BASE HEAD"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from . import zizmor
from .config import CONFIG_FILE, Trust, parse_trust
from .delta import Finding, compare, compare_trust, overall, pin_fix, with_fix
from .github import resolve_sha, upsert_comment
from .powers import is_pinned
from .report import all_findings, render_json, render_markdown, render_text

WORKFLOW_DIR = ".github/workflows/"
ACTION_FILES = ("action.yml", "action.yaml")


def _reviewed(path: str) -> bool:
    """Workflow files, and actions stored in the repository (action.yml)."""
    if path.startswith(WORKFLOW_DIR) and path.endswith((".yml", ".yaml")):
        return True
    return path.rsplit("/", 1)[-1] in ACTION_FILES


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


def compare_commits(base: str, head: str, use_zizmor: bool = False) -> dict[str, list[Finding]]:
    """Compare every workflow file and repository action that differs between two commits.

    A renamed file is compared with its old self, so a rename alone does not
    make every power in the file look new. The trust list (.pipedelta.yml) is
    read from the base commit, so the change under review cannot trust itself.
    """
    results: dict[str, list[Finding]] = {}
    trust = parse_trust(_git_show(base, CONFIG_FILE))
    listing = _git("diff", "--name-status", "-M", "-z", base, head)
    parts = [part for part in listing.split("\0") if part]
    index = 0
    while index < len(parts):
        status = parts[index]
        if status.startswith(("R", "C")) and index + 2 < len(parts):
            old_path, new_path = parts[index + 1], parts[index + 2]
            index += 3
            if status.startswith("C"):
                old_path = new_path  # a copy is a new file
        elif index + 1 < len(parts):
            old_path = new_path = parts[index + 1]
            index += 2
        else:
            break
        if new_path == CONFIG_FILE:
            changes = compare_trust(_git_show(base, old_path), _git_show(head, new_path))
            if changes:
                results[new_path] = changes
        elif _reviewed(new_path) or _reviewed(old_path):
            results[new_path] = _compare_file(
                _git_show(base, old_path), _git_show(head, new_path), new_path, trust, use_zizmor
            )
    return results


def _compare_file(
    before: str | None, after: str | None, path: str, trust: Trust, use_zizmor: bool
) -> list[Finding]:
    findings = compare(before, after, trust)
    if use_zizmor:
        findings = zizmor.merge(findings, zizmor.new_findings(before, after, path))
    return findings


def _resolve_pins(results: dict[str, list[Finding]], token: str) -> None:
    """Fill in the real commit id in each "lock it to a commit" suggestion."""
    cache: dict[str, str | None] = {}
    for findings in results.values():
        for i, f in enumerate(findings):
            if f.power.kind != "action" or is_pinned(f.power.name) or "<40-character" not in f.fix:
                continue
            name = f.power.name
            if name not in cache:
                cache[name] = resolve_sha(name, token)
            if cache[name]:
                findings[i] = with_fix(f, pin_fix(name, cache[name]))


def _merge_base(base: str, head: str) -> str:
    """The commit where the pull request branched off.

    Comparing against the tip of the target branch would blame the pull
    request for anything the target branch removed in the meantime.
    """
    result = subprocess.run(
        ["git", "merge-base", base, head], capture_output=True, text=True, check=False
    )
    found = result.stdout.strip()
    return found if result.returncode == 0 and found else base


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


def _run_action(fail_on: str, use_zizmor: bool) -> int:
    """Entry point when PipeDelta runs as a GitHub Action on a pull request."""
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        event = json.load(handle)
    pr = event.get("pull_request")
    if not pr:
        print("pipedelta: this event is not a pull request, nothing to compare.")
        return 0

    head = pr["head"]["sha"]
    results = compare_commits(_merge_base(pr["base"]["sha"], head), head, use_zizmor)
    token = os.environ.get("PIPEDELTA_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if token:
        _resolve_pins(results, token)
    print(render_text(results))
    markdown = render_markdown(results)

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

    d.add_argument("--config", help="trust list to use (default: none)")

    a = sub.add_parser("action", help="run inside GitHub Actions on a pull request")

    for p in (d, g, a):
        p.add_argument(
            "--fail-on",
            choices=["low", "medium", "high", "never"],
            default="high",
            help="exit with an error if a finding is at or above this level",
        )
        p.add_argument(
            "--zizmor",
            choices=["auto", "on", "off"],
            default="off",
            help="add zizmor's new findings as a second opinion (auto: if installed)",
        )
        p.add_argument(
            "--format", choices=["text", "markdown", "json"], default="text", help="output format"
        )
        p.add_argument(
            "--resolve-pins",
            action="store_true",
            help="look up real commit ids for pin suggestions (uses GITHUB_TOKEN)",
        )

    args = parser.parse_args(argv)
    results: dict[str, list[Finding]] = {}
    if args.zizmor == "on" and not zizmor.available():
        print("pipedelta: --zizmor on, but zizmor is not installed", file=sys.stderr)
        return 2
    use_zizmor = args.zizmor == "on" or (args.zizmor == "auto" and zizmor.available())

    try:
        if args.command == "diff":
            path = args.new if args.new != "-" else args.old
            trust = parse_trust(_read(args.config)) if args.config else Trust()
            results[path] = _compare_file(_read(args.old), _read(args.new), path, trust, use_zizmor)
        elif args.command == "action":
            return _run_action(args.fail_on, use_zizmor)
        else:
            results = compare_commits(args.base, args.head, use_zizmor)
    except (OSError, KeyError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        print(f"pipedelta: {error}", file=sys.stderr)
        return 2
    except yaml.YAMLError as error:
        print(f"pipedelta: could not read a workflow file: {error}", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN", "")
    if args.resolve_pins and token:
        _resolve_pins(results, token)
    if args.format == "markdown":
        print(render_markdown(results))
    elif args.format == "json":
        print(render_json(results))
    else:
        print(render_text(results))
    return _exit_code(results, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
