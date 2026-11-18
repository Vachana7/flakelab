"""Use zizmor, an established GitHub Actions scanner, as a second opinion.

zizmor reports every problem in a file. PipeDelta runs it on the old and the
new version of each changed file and keeps only the problems that are new, then
explains them in the same plain language as its own findings. Where zizmor and
PipeDelta agree, PipeDelta's finding says so instead of repeating it.

zizmor is optional: if it is not installed, this module returns nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .delta import LEVELS, Finding
from .powers import Power, clean

# zizmor audit name -> plain sentence. Unknown audits use zizmor's own text.
PLAIN = {
    "template-injection": "outsider-controlled text is pasted into code the job runs",
    "unpinned-uses": "an outside action is used by a version its author can move",
    "excessive-permissions": "the pipeline token has more permissions than the job needs",
    "dangerous-triggers": "the workflow runs on a trigger outsiders can set off with secrets",
    "artipacked": "the stored checkout token can end up inside an uploaded artifact",
    "cache-poisoning": "a cache shared with release jobs can be filled by untrusted runs",
    "self-hosted-runner": "the job runs on the project's own machine",
    "secrets-inherit": "every secret is handed to a reusable workflow",
    "overprovisioned-secrets": "the job receives every secret at once",
    "unredacted-secrets": "a secret is transformed in a way that hides it from log masking",
    "github-env": "outsider-influenced text is written to GITHUB_ENV or GITHUB_PATH",
    "insecure-commands": "old commands that let output change environment variables are enabled",
    "obfuscation": "an expression is written in a hidden or confusing way",
    "unpinned-images": "a container image is used by a tag its owner can move",
    "hardcoded-container-credentials": "a container password is written in the file",
    "bot-conditions": "a check on the bot's name can be fooled by an outsider",
    "unsound-contains": "a contains() check can be fooled by a crafted value",
    "unsound-condition": "an if: condition is always true because of how it is written",
    "known-vulnerable-actions": "an action version with a published vulnerability is used",
    "impostor-commit": "the action commit does not belong to the action's own repository",
    "ref-confusion": "the action version name matches both a branch and a tag",
    "forbidden-uses": "an action the project has forbidden is used",
    "archived-uses": "an action whose repository is archived is used",
    "use-trusted-publishing": "a long-lived package upload token is used",
}

# zizmor audits that check the same thing as a PipeDelta power kind.
SAME_AS = {
    "template-injection": "injection",
    "unpinned-uses": "action",
    "dangerous-triggers": "trigger",
    "excessive-permissions": "permission",
    "self-hosted-runner": "runner",
    "obfuscation": "hidden",
    "unpinned-images": "container",
    "overprovisioned-secrets": "secret",
    "secrets-inherit": "secret",
}

_SEVERITY = {"high": "high", "medium": "medium", "low": "low", "informational": "low"}


def available() -> bool:
    return shutil.which("zizmor") is not None


def _scan(text: str | None, path: str, tmp: Path) -> list[dict[str, Any]]:
    if not text:
        return []
    name = Path(path).name
    # zizmor decides what a file is from its place and name.
    target = tmp / (name if name in ("action.yml", "action.yaml") else ".github/workflows/" + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [
            "zizmor",
            "--offline",
            "--no-progress",
            "--no-exit-codes",
            "--format",
            "json",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    target.unlink()
    try:
        data = json.loads(result.stdout or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identify one zizmor result in a way that survives unrelated edits.

    The severity is part of the key: a problem that got worse counts as new.
    """
    severity = str(item.get("determinations", {}).get("severity", "")).lower()
    job, feature = "workflow", ""
    for loc in item.get("locations", []):
        if loc.get("symbolic", {}).get("kind") != "Primary":
            continue
        route = loc["symbolic"].get("route", {}).get("route", [])
        if len(route) >= 2 and route[0].get("Key") == "jobs":
            job = str(route[1].get("Key", "workflow"))
        feature = " ".join(str(loc.get("concrete", {}).get("feature", "")).split())
        break
    return (str(item.get("ident", "")), job, feature, severity)


def new_findings(
    before: str | None, after: str | None, path: str
) -> list[tuple[str, str, Finding]]:
    """zizmor results present after the change and not before.

    Returns (audit name, job, finding) for each.
    """
    if not available():
        return []
    with tempfile.TemporaryDirectory(prefix="pipedelta-zizmor-") as tmp:
        old = {_key(i) for i in _scan(before, path, Path(tmp))}
        out = []
        seen = set()
        for item in _scan(after, path, Path(tmp)):
            key = _key(item)
            if key in old or key in seen:
                continue
            seen.add(key)
            ident, job, _, severity = key
            level = _SEVERITY.get(severity, "low")
            place = "the whole workflow" if job == "workflow" else f"job '{clean(job)}'"
            sentence = PLAIN.get(ident) or str(item.get("desc", ident))
            fixes = [f.get("title", "") for f in item.get("fixes", []) if f.get("title")]
            out.append(
                (
                    ident,
                    job,
                    Finding(
                        level,
                        Power("zizmor", clean(ident), clean(job)),
                        f"In {place}, {sentence} (found by zizmor: {ident}).",
                        fixes[0].capitalize() + "." if fixes else "",
                    ),
                )
            )
        return out


def merge(own: list[Finding], extra: list[tuple[str, str, Finding]]) -> list[Finding]:
    """Add zizmor's new results to PipeDelta's, without saying the same thing twice."""
    result = list(own)
    for ident, job, finding in extra:
        kind = SAME_AS.get(ident)
        match = None
        if kind:
            for i, f in enumerate(result):
                same_place = f.power.where == job or kind == "trigger" or job == "workflow"
                if f.power.kind == kind and same_place:
                    match = i
                    break
        if match is not None:
            f = result[match]
            if "zizmor also flags" not in f.message:
                result[match] = Finding(
                    f.level, f.power, f.message + f" zizmor also flags this ({ident}).", f.fix
                )
        else:
            result.append(finding)
    result.sort(key=lambda f: (-LEVELS.index(f.level), f.power))
    return result
