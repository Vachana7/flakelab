"""Compare the powers before and after a change and explain what was gained."""

from __future__ import annotations

from dataclasses import dataclass

from .powers import RISKY_TRIGGERS, Power, action_owner, extract_powers, is_pinned

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

    if kind == "permission":
        writes = name == "write-all" or name.endswith(": write")
        level = "high" if writes else "low"
        verb = "change" if writes else "read"
        return Finding(level, power, f"In {place}, the pipeline token can now {verb}: {name}.")

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

    if kind == "runner":
        return Finding("medium", power, f"In {place}, now runs on the project's own machine.")

    return Finding("low", power, f"New: {kind} {name} in {place}.")


def _combine(findings: list[Finding], gained: set[Power], after: set[Power]) -> list[Finding]:
    """Raise the level when new powers together look like secret theft."""
    jobs_with_new_network = {p.where for p in gained if p.kind == "network"}
    out: list[Finding] = []
    for f in findings:
        p = f.power
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


def compare(before_text: str | None, after_text: str | None) -> list[Finding]:
    """List the powers gained going from the old file to the new file.

    None means the file did not exist on that side.
    """
    before = extract_powers(before_text) if before_text else set()
    after = extract_powers(after_text) if after_text else set()
    gained = {p for p in after - before if not _is_downgrade(p, before)}
    findings = [_explain(p, after) for p in gained]
    findings = _combine(findings, gained, after)
    findings.sort(key=lambda f: (-LEVELS.index(f.level), f.power))
    return findings


def overall(findings: list[Finding]) -> str:
    if not findings:
        return "none"
    return max((f.level for f in findings), key=LEVELS.index)
