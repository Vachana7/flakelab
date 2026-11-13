"""Read one workflow file and list its powers.

A "power" is one thing the pipeline is able to do, for example
"can read the secret AWS_KEY" or "runs when a stranger opens a pull request".
Each power is a small record: (kind, name, where).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

# ${{ secrets.NAME }}
SECRET_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")
# http://host or https://host inside a shell command
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")
# ${{ github.event.<something> }} : text an outsider can control
UNTRUSTED_RE = re.compile(
    r"\$\{\{\s*github\.(event\.(issue|pull_request|comment|review|head_commit|discussion)"
    r"[A-Za-z0-9_.]*|head_ref)\s*\}\}"
)
# a 40-character commit id means the action version cannot be swapped later
PINNED_RE = re.compile(r"@[0-9a-f]{40}$")

# Triggers that let people outside the project start the pipeline
# while it still has access to the project's secrets.
RISKY_TRIGGERS = {"pull_request_target", "workflow_run", "issue_comment"}


@dataclass(frozen=True, order=True)
class Power:
    kind: str  # trigger, permission, secret, action, network, injection, runner
    name: str  # the specific thing, e.g. "AWS_KEY" or "contents: write"
    where: str = "workflow"  # which job it was found in


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _triggers(doc: dict[Any, Any]) -> list[str]:
    # YAML reads the bare word "on" as the boolean True, so check both keys.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(t) for t in on]
    if isinstance(on, dict):
        return [str(t) for t in on]
    return []


def _permissions(value: Any, where: str) -> list[Power]:
    if value is None:
        return []
    if isinstance(value, str):  # "write-all" or "read-all"
        return [Power("permission", value, where)]
    if isinstance(value, dict):
        return [
            Power("permission", f"{scope}: {level}", where)
            for scope, level in value.items()
            if level != "none"
        ]
    return []


def _strings(node: Any) -> list[str]:
    """Every piece of text anywhere inside a YAML value."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def extract_powers(text: str) -> set[Power]:
    """Return the set of powers found in one workflow file's text."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        return set()

    powers: set[Power] = set()

    for trigger in _triggers(doc):
        powers.add(Power("trigger", trigger))

    powers.update(_permissions(doc.get("permissions"), "workflow"))

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}

    # Secrets set at the top of the file are visible to every job.
    for s in _strings(doc.get("env")):
        for name in SECRET_RE.findall(s):
            powers.add(Power("secret", name, "workflow"))

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        where = str(job_name)
        powers.update(_permissions(job.get("permissions"), where))

        for label in _as_list(job.get("runs-on")):
            if isinstance(label, str) and "self-hosted" in label:
                powers.add(Power("runner", "self-hosted", where))

        if isinstance(job.get("uses"), str):  # a reusable workflow
            powers.add(Power("action", job["uses"], where))
        if job.get("secrets") == "inherit":
            powers.add(Power("secret", "(all secrets, inherited)", where))

        for s in _strings(job):
            for name in SECRET_RE.findall(s):
                powers.add(Power("secret", name, where))

        for step in _as_list(job.get("steps")):
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if isinstance(uses, str) and not uses.startswith("./"):
                powers.add(Power("action", uses, where))
            run = step.get("run")
            if isinstance(run, str):
                for host in URL_RE.findall(run):
                    powers.add(Power("network", host.lower().rstrip("."), where))
                if UNTRUSTED_RE.search(run):
                    powers.add(
                        Power(
                            "injection", "outsider-controlled text used in a shell command", where
                        )
                    )
    return powers


def is_pinned(action: str) -> bool:
    return bool(PINNED_RE.search(action)) or action.startswith("docker://") and "@sha256:" in action


def action_owner(action: str) -> str:
    return action.split("/", 1)[0].lower()
