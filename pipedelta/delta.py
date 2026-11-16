"""Compare the powers before and after a change and explain what was gained."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import yaml

from .permissions import (
    CANNOT_TELL,
    INCREASE,
    NONE,
    OTHER_SCOPES,
    RANK,
    REDUCTION,
    UNKNOWN,
    WRITE,
    Change,
    Token,
    compare_tokens,
    job_tokens,
)
from .powers import (
    BUILT_IN_TOKEN,
    RISKY_TRIGGERS,
    Power,
    action_name,
    action_owner,
    extract_powers,
    is_pinned,
)

# Action publishers that come from GitHub itself.
FIRST_PARTY = {"actions", "github"}

LEVELS = ["low", "medium", "high"]


@dataclass(frozen=True)
class Finding:
    level: str  # low, medium, high
    power: Power
    message: str  # one plain sentence
    # "gained": the pipeline can do something new (the default).
    # "reduced": the pipeline can do less than before. Shown, never fails the check.
    # "unknown": something changed but the file does not say in which direction.
    change: str = "gained"


def _explain(power: Power, after: set[Power]) -> Finding:
    kind, name, where = power.kind, power.name, power.where
    place = "the whole workflow" if where == "workflow" else f"job '{where}'"

    if kind == "trigger":
        if name in RISKY_TRIGGERS:
            return Finding(
                "high",
                power,
                f"Now runs on '{name}', which people outside the project can set off "
                "while the pipeline still has access to secrets.",
            )
        return Finding("low", power, f"Now also runs on '{name}'.")

    if kind == "secret" and name == BUILT_IN_TOKEN:
        return Finding(
            "low",
            power,
            f"In {place}, now passes the pipeline's own token (GITHUB_TOKEN) to a step. "
            "What it can do is set by the permissions.",
        )

    if kind == "secret":
        return Finding("medium", power, f"In {place}, can now read the secret {name}.")

    if kind == "action":
        if action_owner(name) in FIRST_PARTY:
            return Finding("low", power, f"In {place}, now runs GitHub's own action {name}.")
        if is_pinned(name):
            return Finding(
                "medium",
                power,
                f"In {place}, now runs outside code {name} (version locked to one commit).",
            )
        return Finding(
            "high",
            power,
            f"In {place}, now runs outside code {name}, and its author can change "
            "what that version does at any time.",
        )

    if kind == "network":
        return Finding("medium", power, f"In {place}, a command now contacts {name}.")

    if kind == "injection":
        return Finding(
            "high",
            power,
            f"In {place}, text written by an outsider (such as a pull request title) "
            "is pasted into a shell command, so they can run their own commands.",
        )

    if kind == "hidden":
        return Finding(
            "high",
            power,
            f"In {place}, a command decodes hidden text and runs it, "
            "so a reviewer cannot see what it does.",
        )

    if kind == "runner":
        return Finding("medium", power, f"In {place}, now runs on the project's own machine.")

    return Finding("low", power, f"New: {kind} {name} in {place}.")


def _combine(findings: list[Finding], gained: set[Power], after: set[Power]) -> list[Finding]:
    """Raise the level when new powers together look like secret theft."""
    jobs_with_new_network = {p.where for p in gained if p.kind == "network"}
    out: list[Finding] = []
    for f in findings:
        p = f.power
        if p not in gained:
            out.append(f)
            continue
        if p.kind == "network":
            secrets_here = [
                s for s in after if s.kind == "secret" and s.where in (p.where, "workflow")
            ]
            if secrets_here:
                f = Finding(
                    "high",
                    p,
                    f.message + " The same job can read secrets, so they could be sent there.",
                )
        elif p.kind == "secret" and p.where in jobs_with_new_network:
            f = Finding("high", p, f.message)
        out.append(f)
    return out


def _already_had(power: Power, before: set[Power]) -> Finding | None:
    """Handle powers the workflow already had in some form before the change.

    Renaming a job or raising an action's version number changes the text of
    the file without giving the pipeline anything it could not do before.
    Returns a low-level note for those cases, or None if the power is new.
    """
    place = "the whole workflow" if power.where == "workflow" else f"job '{power.where}'"

    if power.kind == "action":
        same_tool = [
            b
            for b in before
            if b.kind == "action" and action_name(b.name) == action_name(power.name)
        ]
        if not same_tool:
            return None
        if any(b.name == power.name for b in same_tool):
            return Finding("low", power, f"{power.name} was already used; now also in {place}.")
        was_pinned = all(is_pinned(b.name) for b in same_tool)
        if was_pinned and not is_pinned(power.name):
            return Finding(
                "high",
                power,
                f"In {place}, {action_name(power.name)} was locked to one commit and is now "
                f"referenced as {power.name}, which its author can change at any time.",
            )
        return Finding(
            "low",
            power,
            f"In {place}, the version of {action_name(power.name)} changed to {power.name}.",
        )

    same_power_existed = any(b.kind == power.kind and b.name == power.name for b in before)
    if power.kind in ("secret", "network", "runner", "injection", "hidden") and same_power_existed:
        return Finding(
            "low",
            power,
            f"Already present in this workflow; now also in {place}: {power.name}.",
        )
    return None


NOTHING = Token(default=NONE)  # what a job that did not exist before could do


def _place(jobs: list[str]) -> str:
    """'job a' / 'jobs a, b' / 'jobs a, b, c and 2 more'."""
    quoted = [f"'{job}'" for job in jobs]
    if len(quoted) == 1:
        return f"job {quoted[0]}"
    if len(quoted) <= 3:
        return "jobs " + ", ".join(quoted)
    return "jobs " + ", ".join(quoted[:3]) + f" and {len(quoted) - 3} more"


def _held_before(change: Change, before: Iterable[Token]) -> bool:
    """Did some job already have this level for this scope before the change?

    Used only for jobs with a new name, so that renaming a job is not
    reported as the pipeline gaining permissions it already had.
    """
    for token in before:
        had = token.default if change.scope == OTHER_SCOPES else token.level(change.scope)
        if change.new == UNKNOWN:
            if had == UNKNOWN:
                return True
        elif had != UNKNOWN and RANK[had] >= RANK[change.new]:
            return True
    return False


def _permission_finding(change: Change, jobs: list[str], held_before: bool) -> Finding:
    place = _place(jobs)
    scope, old, new = change.scope, change.old, change.new
    power = Power("permission", f"{scope}: {new}", ", ".join(jobs))

    if held_before:
        return Finding(
            "low",
            power,
            f"In {place}, the pipeline token has {scope}: {new}. "
            "Another job already had this before the change.",
        )

    if change.kind == INCREASE:
        if new == WRITE:
            return Finding(
                "high",
                power,
                f"In {place}, the pipeline token can now change {scope} (was {old}, now write).",
            )
        return Finding(
            "low", power, f"In {place}, the pipeline token can now read {scope} (was {old})."
        )

    if change.kind == REDUCTION:
        return Finding(
            "low",
            power,
            f"In {place}, the pipeline token lost access to {scope} (was {old}, now {new}).",
            change="reduced",
        )

    # The file does not say whether this is more or less than before.
    assert change.kind == CANNOT_TELL
    if new == UNKNOWN and scope == OTHER_SCOPES:
        text = (
            f"In {place}, the pipeline token's permissions cannot be read from this file: "
            "no limit is set (or it is written in a form PipeDelta does not recognise), so the "
            f"repository's default applies, which may include changing the repository (was {old})."
        )
        level = "medium"
    elif new == UNKNOWN:
        text = (
            f"In {place}, the level of {scope} cannot be determined from the file "
            f"(was {old}). The value may not be valid for this scope."
        )
        level = "medium"
    else:
        text = (
            f"In {place}, {scope} is now set to {new}. Before, the file did not say what "
            "it was, so PipeDelta cannot tell whether this is more or less than before."
        )
        level = "medium" if new == WRITE else "low"
    return Finding(level, power, text, change="unknown")


def _permission_findings(before_text: str | None, after_text: str | None) -> list[Finding]:
    """Compare what each job's token gets before and after the change."""
    before = job_tokens(yaml.safe_load(before_text)) if before_text else {}
    after = job_tokens(yaml.safe_load(after_text)) if after_text else {}

    # The same change in several jobs (for example when the workflow-level
    # block changes) becomes one finding that names all of them.
    grouped: dict[tuple[Change, bool], list[str]] = {}
    for job, token in after.items():
        if job in before:
            for change in compare_tokens(before[job], token):
                grouped.setdefault((change, False), []).append(job)
        else:
            for change in compare_tokens(NOTHING, token):
                held = _held_before(change, before.values())
                grouped.setdefault((change, held), []).append(job)
    return [_permission_finding(change, jobs, held) for (change, held), jobs in grouped.items()]


def compare(before_text: str | None, after_text: str | None) -> list[Finding]:
    """List what changed in the pipeline's powers from the old file to the new file.

    None means the file did not exist on that side.
    """
    before = extract_powers(before_text) if before_text else set()
    after = extract_powers(after_text) if after_text else set()
    # Permissions are handled separately below, from each job's effective token.
    gained = {p for p in after - before if p.kind != "permission"}

    findings: list[Finding] = []
    truly_new: set[Power] = set()
    for power in gained:
        note = _already_had(power, before)
        if note is not None:
            findings.append(note)
        else:
            truly_new.add(power)
            findings.append(_explain(power, after))
    findings = _combine(findings, truly_new, after)
    findings += _permission_findings(before_text, after_text)
    findings.sort(key=lambda f: (f.change == "reduced", -LEVELS.index(f.level), f.power))
    return findings


def overall(findings: list[Finding]) -> str:
    """The highest level among findings that are not reductions."""
    counted = [f for f in findings if f.change != "reduced"]
    if not counted:
        return "none"
    return max((f.level for f in counted), key=LEVELS.index)
