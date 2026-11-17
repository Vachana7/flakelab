"""Turns the PipeDelta engine's output into the JSON the web app shows.

Nothing here decides a risk level. The engine does (``delta.compare``). This
module only runs it on the right files, adds evidence (``evidence.explain``),
and arranges the result: summary, findings, jobs and steps, attack paths and a
side-by-side diff.
"""

from __future__ import annotations

import difflib
import secrets
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import yaml

from ..evidence import SourceMap, explain
from ..jobs import job_facts
from ..paths import new_paths, paths_in
from ..permissions import READ, WRITE, job_tokens
from ..text import CONTROL_RE
from .github_client import (
    GitHub,
    GitHubError,
    check_ref,
    check_workflow_path,
    parse_repository,
)

MAX_DIFF_LINES = 3000
NOT_COUNTED = ("reduced", "improved")


class InputError(Exception):
    """The request itself is wrong. Shown to the user as is."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str, limit: int = 200) -> str:
    return CONTROL_RE.sub("", value).strip()[:limit]


# ---- one file --------------------------------------------------------------------------


def summarize(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts and the overall level. Removed and improved powers never count."""
    counted = [e for e in evidence if e["change"] not in NOT_COUNTED]
    counts = {"high": 0, "medium": 0, "low": 0}
    for e in counted:
        counts[e["severity"]] += 1
    level = next((name for name in ("high", "medium", "low") if counts[name]), "none")
    return {
        "level": level,
        "counts": counts,
        "gained": len(counted),
        "reduced": sum(1 for e in evidence if e["change"] == "reduced"),
        "improved": sum(1 for e in evidence if e["change"] == "improved"),
        "kinds": dict(Counter(e["kind"] for e in counted)),
        "confidence": dict(Counter(e["confidence"] for e in counted)),
        "would_fail": level == "high",  # the default gate of the GitHub Action
    }


def _token_view(token: Any) -> dict[str, Any]:
    if not token.known:
        return {"known": False, "default": None, "scopes": {}}
    scopes = {scope: level for scope, level in token.scopes if level in (READ, WRITE)}
    return {"known": True, "default": token.default, "scopes": scopes}


def _runs_on(smap: SourceMap, job_name: str) -> str:
    site = smap.jobs.get(job_name)
    entry = site.fields.get("runs-on") if site else None
    if entry is None:
        return ""
    line = smap.lines[entry[0]] if entry[0] < len(smap.lines) else ""
    return clean_text(line.split(":", 1)[1] if ":" in line else line, 80)


def structure(text: str | None, evidence: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """Jobs, their steps and the facts the engine collected about each job."""
    if not text:
        return {"jobs": [], "paths": []}
    smap = SourceMap(text)
    facts = job_facts(text)
    tokens = job_tokens(yaml.safe_load(text))
    jobs: list[dict[str, Any]] = []
    for name, site in smap.jobs.items():
        fact = facts.get(name)
        steps = [
            {
                "index": i,
                "label": step.label,
                "kind": step.kind,
                "line": step.span.first + 1,
                "findings": [
                    e["id"]
                    for e in evidence
                    if e["job"] == name and e["step"] == i and e["side"] == side
                ],
            }
            for i, step in enumerate(site.steps, start=1)
        ]
        jobs.append(
            {
                "name": name,
                "line": site.key_line + 1,
                "runs_on": _runs_on(smap, name),
                "token": _token_view(tokens[name]) if name in tokens else None,
                "secrets": sorted(fact.secrets) if fact else [],
                "hosts": sorted(fact.hosts) if fact else [],
                "unpinned": sorted(fact.unpinned) if fact else [],
                "write_scopes": sorted(fact.write_scopes) if fact else [],
                "self_hosted": bool(fact and fact.self_hosted),
                "outsider_text": bool(fact and fact.injection),
                "hidden": bool(fact and fact.hidden),
                "findings": [e["id"] for e in evidence if e["job"] == name and e["side"] == side],
                "steps": steps,
            }
        )
    return {"jobs": jobs}


def attack_paths(before: str | None, after: str | None) -> list[dict[str, Any]]:
    """Dangerous pairings inside one job, with whether this change made them possible."""
    if not after:
        return []
    fresh = set(new_paths(before, after)) if before else set(paths_in(after))
    return [
        {
            "rule": path.rule,
            "level": path.level,
            "reason": path.reason,
            "jobs": list(path.jobs),
            "new": path in fresh,
        }
        for path in paths_in(after)
    ]


def diff_rows(
    before: str | None, after: str | None, evidence: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """A side-by-side diff. Each row can carry the ids of findings on its lines."""
    if before is None or after is None:
        return None
    old, new = before.splitlines(), after.splitlines()
    if len(old) > MAX_DIFF_LINES or len(new) > MAX_DIFF_LINES:
        return {"too_large": True, "rows": []}

    on_old: dict[int, list[str]] = {}
    on_new: dict[int, list[str]] = {}
    for e in evidence:
        if e["line"] is not None:
            (on_old if e["side"] == "before" else on_new).setdefault(e["line"], []).append(e["id"])

    def cell(lines: list[str], n: int, marks: dict[int, list[str]]) -> dict[str, Any]:
        return {"n": n + 1, "text": clean_text(lines[n], 400), "findings": marks.get(n + 1, [])}

    rows: list[dict[str, Any]] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(
                    {"t": "eq", "a": cell(old, i1 + k, on_old), "b": cell(new, j1 + k, on_new)}
                )
            continue
        height = max(i2 - i1, j2 - j1)
        for k in range(height):
            a = cell(old, i1 + k, on_old) if i1 + k < i2 else None
            b = cell(new, j1 + k, on_new) if j1 + k < j2 else None
            kind = "chg" if a and b else "del" if a else "add"
            rows.append({"t": kind, "a": a, "b": b})
    return {"too_large": False, "rows": rows}


def analyze_file(path: str, before: str | None, after: str | None, status: str) -> dict[str, Any]:
    """Everything about one workflow file in one change (or on its own)."""
    findings = [e.to_dict() for e in explain(before, after, path)]
    side_text = after if after is not None else before
    return {
        "path": clean_text(path),
        "status": status,
        "summary": summarize(findings),
        "findings": findings,
        "structure": structure(side_text, findings, "after" if after is not None else "before"),
        "paths": attack_paths(before, after),
        "diff": diff_rows(before, after, findings),
        "before_text": before,
        "after_text": after,
    }


def combine(files: list[dict[str, Any]]) -> dict[str, Any]:
    """The summary of an analysis that covers several files."""
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    level = max((f["summary"]["level"] for f in files), key=lambda v: order[v], default="none")
    counts = {"high": 0, "medium": 0, "low": 0}
    kinds: Counter[str] = Counter()
    confidence: Counter[str] = Counter()
    gained = reduced = improved = 0
    for f in files:
        s = f["summary"]
        for name in counts:
            counts[name] += s["counts"][name]
        kinds.update(s["kinds"])
        confidence.update(s["confidence"])
        gained += s["gained"]
        reduced += s["reduced"]
        improved += s["improved"]
    return {
        "level": level,
        "counts": counts,
        "gained": gained,
        "reduced": reduced,
        "improved": improved,
        "kinds": dict(kinds),
        "confidence": dict(confidence),
        "files": len(files),
        "would_fail": level == "high",
    }


# ---- the service -------------------------------------------------------------------------


class AnalysisService:
    """Fetches from GitHub, runs the engine, stores and returns the result."""

    def __init__(self, github: GitHub, store: Any) -> None:
        self.github = github
        self.store = store

    # -- repositories --

    def connect(self, text: str) -> dict[str, Any]:
        owner, name = parse_repository(text)
        repo = self.github.repository(owner, name)
        workflows = self.github.workflows(owner, name, repo["default_branch"])
        self.store.save_repo(repo)
        return {"repo": repo, "workflows": workflows}

    def workflows(self, text: str, ref: str | None) -> dict[str, Any]:
        owner, name = parse_repository(text)
        repo = self.github.repository(owner, name)
        ref = check_ref(ref) or repo["default_branch"]
        return {"repo": repo, "ref": ref, "workflows": self.github.workflows(owner, name, ref)}

    def file_history(self, text: str, path: str, ref: str | None) -> list[dict[str, Any]]:
        owner, name = parse_repository(text)
        return self.github.file_commits(owner, name, check_workflow_path(path), check_ref(ref))

    def pulls(self, text: str) -> list[dict[str, Any]]:
        owner, name = parse_repository(text)
        return self.github.pulls(owner, name)

    # -- analyses --

    def _finish(self, result: dict[str, Any]) -> dict[str, Any]:
        result["id"] = secrets.token_hex(6)
        result["created_at"] = now()
        result["summary"] = combine(result["files"])
        self.store.save_analysis(result)
        return result

    def inventory(self, text: str, path: str, ref: str | None) -> dict[str, Any]:
        """What one workflow file, as it is now, is able to do."""
        owner, name = parse_repository(text)
        path = check_workflow_path(path)
        repo = self.github.repository(owner, name)
        ref = check_ref(ref) or repo["default_branch"]
        content = self.github.file(owner, name, path, ref)
        yaml_error = _yaml_problem(content)
        if yaml_error:
            raise InputError("bad_yaml", yaml_error, 422)
        file_result = analyze_file(path, None, content, "inventory")
        return self._finish(
            {
                "mode": "inventory",
                "source": "github",
                "repo": repo["full_name"],
                "title": f"{repo['full_name']} · {path.rsplit('/', 1)[-1]}",
                "refs": {"base": None, "head": {"label": ref, "sha": None}},
                "pull": None,
                "files": [file_result],
            }
        )

    def compare(
        self, text: str, path: str, base: str | None, head: str | None, ref: str | None
    ) -> dict[str, Any]:
        """One workflow file at two commits: what the newer one can do that the older could not."""
        owner, name = parse_repository(text)
        path = check_workflow_path(path)
        repo = self.github.repository(owner, name)
        base, head = check_ref(base), check_ref(head)
        if head is None or base is None:
            history = self.github.file_commits(
                owner, name, path, check_ref(ref) or repo["default_branch"]
            )
            if head is None:
                if not history:
                    raise InputError("no_history", "This file has no commits to compare.", 404)
                head = history[0]["sha"]
            if base is None:
                later = [c for c in history if c["sha"] != head]
                position = next((i for i, c in enumerate(history) if c["sha"] == head), -1)
                older = history[position + 1 :] if position >= 0 else later
                base = older[0]["sha"] if older else None
        before = self._file_or_none(owner, name, path, base) if base else None
        after = self.github.file(owner, name, path, head)
        for label, content in (("older", before), ("newer", after)):
            problem = _yaml_problem(content) if content is not None else None
            if problem:
                raise InputError("bad_yaml", f"The {label} version: {problem}", 422)
        status = "added" if before is None else "modified"
        return self._finish(
            {
                "mode": "compare",
                "source": "github",
                "repo": repo["full_name"],
                "title": f"{repo['full_name']} · {path.rsplit('/', 1)[-1]}",
                "refs": {
                    "base": {"label": (base or "none")[:7], "sha": base},
                    "head": {"label": head[:7], "sha": head},
                },
                "pull": None,
                "files": [analyze_file(path, before, after, status)],
            }
        )

    def pull_request(self, text: str, number: int) -> dict[str, Any]:
        """What a pull request changes in the workflow files: the real PipeDelta use case."""
        owner, name = parse_repository(text)
        pull = self.github.pull(owner, name, number)
        base_sha = pull["base"]["sha"]
        head_repo = (pull["head"].get("repo") or {}).get("full_name")
        if not head_repo:
            raise InputError("no_head", "The branch this pull request came from was deleted.", 410)
        head_owner, head_name = head_repo.split("/", 1)
        head_sha = pull["head"]["sha"]

        files: list[dict[str, Any]] = []
        for item in self.github.pull_files(owner, name, number):
            path = str(item.get("filename", ""))
            if not (path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))):
                continue
            status = str(item.get("status", "modified"))
            old_path = str(item.get("previous_filename") or path)
            before = (
                None if status == "added" else self._file_or_none(owner, name, old_path, base_sha)
            )
            after = (
                None
                if status == "removed"
                else self.github.file(head_owner, head_name, path, head_sha)
            )
            for label, content in (("old", before), ("new", after)):
                problem = _yaml_problem(content) if content is not None else None
                if problem:
                    raise InputError("bad_yaml", f"{path} ({label} version): {problem}", 422)
            files.append(analyze_file(path, before, after, status))
        return self._finish(
            {
                "mode": "pull",
                "source": "github",
                "repo": f"{owner}/{name}",
                "title": f"{owner}/{name} · PR #{number}",
                "refs": {
                    "base": {"label": base_sha[:7], "sha": base_sha},
                    "head": {"label": head_sha[:7], "sha": head_sha},
                },
                "pull": {
                    "number": number,
                    "title": clean_text(str(pull.get("title", ""))),
                    "url": pull.get("html_url"),
                    "author": (pull.get("user") or {}).get("login", ""),
                },
                "files": files,
            }
        )

    def pasted(
        self, name: str, before: str | None, after: str, source: str = "paste"
    ) -> dict[str, Any]:
        """Workflow text given directly (pasted or loaded from a sample), no GitHub needed."""
        for label, content in (("old", before), ("new", after)):
            problem = _yaml_problem(content) if content else None
            if problem:
                raise InputError("bad_yaml", f"The {label} workflow: {problem}", 422)
        label = clean_text(name or "workflow.yml", 100)
        has_before = before is not None and before.strip() != ""
        file_result = analyze_file(
            label, before if has_before else None, after, "modified" if has_before else "inventory"
        )
        return self._finish(
            {
                "mode": "compare" if has_before else "inventory",
                "source": source,
                "repo": None,
                "title": label,
                "refs": {"base": None, "head": None},
                "pull": None,
                "files": [file_result],
            }
        )

    def _file_or_none(self, owner: str, name: str, path: str, ref: str) -> str | None:
        try:
            return self.github.file(owner, name, path, ref)
        except GitHubError as error:
            if error.code == "not_found":
                return None  # the file did not exist at that commit
            raise


def _yaml_problem(text: str | None) -> str | None:
    """A sentence about why this text cannot be read as a workflow, or None."""
    if text is None:
        return None
    if len(text) > 256 * 1024:
        return "The file is larger than 256 KB."
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark is not None else ""
        return f"This is not valid YAML{where}."
    if not isinstance(doc, dict):
        return "This does not look like a workflow: it is not a YAML mapping."
    if "jobs" not in doc:
        return "This does not look like a workflow: it has no 'jobs' section."
    return None
