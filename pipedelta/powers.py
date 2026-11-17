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

from . import expressions
from .text import clean

# http://host or https://host inside a shell command
# A web address, capturing the host. An address may carry a login in front of
# the host (https://user:password@host/); that part is skipped, because it is
# not where the command connects to. The login ends at the first "@" and cannot
# contain "/", so an "@" later in the path or query is not mistaken for one.
# The password may be a GitHub expression, which contains spaces.
_LOGIN = r"""(?:(?:\$\{\{[^}\n]{0,200}\}\}|[^\s/@'"])*@)?"""
URL_RE = re.compile(r"https?://" + _LOGIN + r"([A-Za-z0-9.-]+)")
# text that is decoded and immediately run, so a reviewer cannot read what it does
HIDDEN_RE = re.compile(
    r"base64\s+(-d|-D|--decode)\b[^\n]*\|\s*(ba|z)?sh\b"
    r"|eval\s+[\"']?\$\([^)]*base64\s+(-d|-D|--decode)"
)
# a 40-character commit id means the action version cannot be swapped later
PINNED_RE = re.compile(r"@[0-9a-f]{40}$")

# Triggers that let people outside the project start the pipeline
# while it still has access to the project's secrets.
RISKY_TRIGGERS = {"pull_request_target", "workflow_run", "issue_comment"}


@dataclass(frozen=True, order=True)
class Power:
    kind: str  # trigger, permission, secret, action, network, injection, runner, hidden
    name: str  # the specific thing, e.g. "AWS_KEY" or "contents: write"
    where: str = "workflow"  # which job it was found in


# Action publishers that are GitHub itself.
FIRST_PARTY = {"actions", "github"}

NO_LIMIT = "repository default (no limit set in the file)"
BUILT_IN_TOKEN = "GITHUB_TOKEN"


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
        return [Power("permission", clean(value), where)]
    if isinstance(value, dict):
        return [
            Power("permission", clean(f"{scope}: {level}"), where)
            for scope, level in value.items()
            if level != "none"
        ]
    return []


def _strings(node: Any) -> list[str]:
    """Every piece of text anywhere inside a YAML value.

    The value of an ``if:`` key is an expression even without ``${{ }}``
    around it, so it is wrapped to be read as one.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            if key == "if" and isinstance(value, str) and "${{" not in value:
                found.append("${{ " + value + " }}")
            else:
                found.extend(_strings(value))
        return found
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


INJECTION = "outsider-controlled text used in a shell command"
ALL_SECRETS = expressions.ALL_SECRETS  # kept under this name for existing imports


def _secret_names(text: str) -> set[str]:
    """Secrets referenced by the ``${{ ... }}`` expressions in one string."""
    names: set[str] = set()
    for body in expressions.bodies(text):
        names |= expressions.secret_names(body)
    return names


def extract_powers(text: str) -> set[Power]:
    """Return the set of powers found in one workflow file's text."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        return set()

    powers: set[Power] = set()

    for trigger in _triggers(doc):
        powers.add(Power("trigger", clean(trigger)))

    powers.update(_permissions(doc.get("permissions"), "workflow"))
    limited_for_all_jobs = "permissions" in doc

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}

    # Secrets set at the top of the file are visible to every job.
    for s in _strings(doc.get("env")):
        for name in _secret_names(s):
            powers.add(Power("secret", name, "workflow"))

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        where = clean(job_name)
        powers.update(_permissions(job.get("permissions"), where))
        if not limited_for_all_jobs and "permissions" not in job:
            # With no limit written anywhere, the token gets whatever the
            # repository's default is, which can include write access.
            powers.add(Power("permission", NO_LIMIT, where))

        runs_on = job.get("runs-on")
        if isinstance(runs_on, dict):  # the "group / labels" form
            runs_on = runs_on.get("labels")
        for label in _as_list(runs_on):
            if isinstance(label, str) and "self-hosted" in label:
                powers.add(Power("runner", "self-hosted", where))

        reusable = job.get("uses")
        # A reusable workflow from another repository is outside code.
        # One that starts with "./" lives in this repository and is reviewed here.
        if isinstance(reusable, str) and not reusable.startswith("./"):
            powers.add(Power("action", clean(reusable), where))
        if job.get("secrets") == "inherit":
            powers.add(Power("secret", "(all secrets, inherited)", where))

        for s in _strings(job):
            for name in _secret_names(s):
                powers.add(Power("secret", name, where))

        for step in _as_list(job.get("steps")):
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if isinstance(uses, str) and not uses.startswith("./"):
                powers.add(Power("action", clean(uses), where))
            run = step.get("run")
            if isinstance(run, str):
                for host in URL_RE.findall(run):
                    powers.add(Power("network", host.lower().rstrip("."), where))
                if HIDDEN_RE.search(run):
                    powers.add(Power("hidden", "decodes hidden text and runs it", where))
                if expressions.has_untrusted_value(run):
                    powers.add(Power("injection", INJECTION, where))
            # The same substitution happens in the script of a github-script
            # step, where the pasted text becomes JavaScript.
            script = (
                step.get("with", {}).get("script") if isinstance(step.get("with"), dict) else None
            )
            if (
                isinstance(uses, str)
                and action_name(uses) == "actions/github-script"
                and isinstance(script, str)
                and expressions.has_untrusted_value(script)
            ):
                powers.add(Power("injection", INJECTION, where))
    return powers


def is_pinned(action: str) -> bool:
    return bool(PINNED_RE.search(action)) or action.startswith("docker://") and "@sha256:" in action


def action_name(action: str) -> str:
    """The action without its version: 'owner/tool@v1' -> 'owner/tool'."""
    return action.split("@", 1)[0].lower()


def action_owner(action: str) -> str:
    return action.split("/", 1)[0].lower()
