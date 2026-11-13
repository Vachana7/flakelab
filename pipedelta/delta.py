"""Compare the powers before and after a change and explain what was gained."""

from __future__ import annotations

from dataclasses import dataclass

from .powers import (
    BUILT_IN_TOKEN,
    NO_LIMIT,
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

    if kind == "permission" and name == NO_LIMIT:
        return Finding(
            "medium",
            power,
            f"In {place}, no limit is set on the pipeline token, so it gets the "
            "repository's default permissions, which may include changing the repository.",
        )

    if kind == "permission":
        writes = name == "write-all" or name.endswith(": write")
        level = "high" if writes else "low"
        verb = "change" if writes else "read"
        return Finding(level, power, f"In {place}, the pipeline token can now {verb}: {name}.")

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


def _is_downgrade(power: Power, before: set[Power]) -> bool:
    """Going from write to read is losing a power, not gaining one."""
    if power.kind != "permission" or not power.name.endswith(": read"):
        return False
    scope = power.name.split(":")[0]
    wider = {f"{scope}: write", "write-all"}
    return any(b.kind == "permission" and b.name in wider for b in before)


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

    if power.kind == "permission":
        if any(b.kind == "permission" and b.name in (power.name, "write-all") for b in before):
            return Finding(
                "low",
                power,
                f"The token permission '{power.name}' already existed; now set in {place}.",
            )
        return None

    same_power_existed = any(b.kind == power.kind and b.name == power.name for b in before)
    if power.kind in ("secret", "network", "runner", "injection", "hidden") and same_power_existed:
        return Finding(
            "low",
            power,
            f"Already present in this workflow; now also in {place}: {power.name}.",
        )
    return None


def compare(before_text: str | None, after_text: str | None) -> list[Finding]:
    """List the powers gained going from the old file to the new file.

    None means the file did not exist on that side.
    """
    before = extract_powers(before_text) if before_text else set()
    after = extract_powers(after_text) if after_text else set()
    gained = {p for p in after - before if not _is_downgrade(p, before)}

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
    findings.sort(key=lambda f: (-LEVELS.index(f.level), f.power))
    return findings


def overall(findings: list[Finding]) -> str:
    if not findings:
        return "none"
    return max((f.level for f in findings), key=LEVELS.index)
