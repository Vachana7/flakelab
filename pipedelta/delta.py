"""Compare the powers before and after a change and explain what was gained."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Trust, parse_trust
from .powers import (
    BUILT_IN_TOKEN,
    NO_LIMIT,
    RISKY_TRIGGERS,
    RUNTIME_ADDRESS,
    Power,
    action_name,
    action_owner,
    clean,
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
    fix: str = ""  # how to remove the risk, when there is a simple way


def with_fix(finding: Finding, fix: str) -> Finding:
    return Finding(finding.level, finding.power, finding.message, fix)


def pin_fix(action: str, sha: str | None = None) -> str:
    """The line to write instead of an action referenced by a movable tag."""
    name, _, version = action.partition("@")
    commit = sha or "<40-character commit id of " + (version or "the version you use") + ">"
    comment = f"  # {version}" if version else ""
    return f"Lock it to one commit: `uses: {name}@{commit}{comment}`"


_INJECTION_FIX = (
    "Pass the value in an environment variable and quote it: "
    '`env: { VALUE: ${{ github.event... }} }` then use "$VALUE" in the command.'
)


def _place(where: str) -> str:
    if where == "workflow":
        return "the whole workflow"
    if where == "(action file)":
        return "this repository action"
    return f"job '{where}'"


def _explain(power: Power, after: set[Power]) -> Finding:
    kind, name, where = power.kind, power.name, power.where
    place = _place(where)

    if kind == "trigger":
        if name in RISKY_TRIGGERS:
            return Finding(
                "high",
                power,
                f"Now runs on '{name}', which people outside the project can set off "
                "while the pipeline still has access to secrets.",
                "Use 'pull_request' if the workflow only needs to test the change. If it "
                "must use this trigger, never check out or run the pull request's code in it.",
            )
        return Finding("low", power, f"Now also runs on '{name}'.")

    if kind == "permission" and name == NO_LIMIT:
        return Finding(
            "medium",
            power,
            f"In {place}, no limit is set on the pipeline token, so it gets the "
            "repository's default permissions, which may include changing the repository.",
            "Add `permissions: { contents: read }` at the top of the file and widen only "
            "the jobs that need more.",
        )

    if kind == "permission":
        writes = name == "write-all" or name.endswith(": write")
        level = "high" if writes else "low"
        verb = "change" if writes else "read"
        fix = (
            "Give write access only to the job that needs it, and only for that scope."
            if writes
            else ""
        )
        if name == "write-all":
            fix = "Replace write-all with the few scopes the job needs, e.g. `contents: read`."
        return Finding(level, power, f"In {place}, the pipeline token can now {verb}: {name}.", fix)

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
            pin_fix(name),
        )

    if kind == "network" and name == RUNTIME_ADDRESS:
        return Finding(
            "medium",
            power,
            f"In {place}, a command now sends a request to an address that is only known "
            "when the job runs, so a reviewer cannot check where data goes.",
            "Write the address in the file so reviewers can see it.",
        )

    if kind == "network":
        return Finding("medium", power, f"In {place}, a command now contacts {name}.")

    if kind == "local":
        return Finding(
            "low",
            power,
            f"In {place}, now runs the action {name} stored in this repository. "
            "If this change also edits that action, its powers are listed under its own file.",
        )

    if kind == "container":
        image = name
        official = "/" not in image.split("@", 1)[0].split(":", 1)[0]
        if official or "@sha256:" in image:
            return Finding("low", power, f"In {place}, now uses the container image {image}.")
        return Finding(
            "medium",
            power,
            f"In {place}, now uses the outside container image {image}, which its "
            "owner can replace at any time.",
            f"Lock the image to a digest: `{image.split(':', 1)[0]}@sha256:<digest>`.",
        )

    if kind == "code":
        return Finding(
            "medium",
            power,
            f"This action {name}. PipeDelta cannot read inside that code; review it by hand.",
        )

    if kind == "guard":
        return Finding(
            "high",
            power,
            "This change removes the PipeDelta check from the workflow, so later "
            "changes would no longer be reviewed.",
            "Keep the PipeDelta step, and mark its check as required in the branch rules.",
        )

    if kind == "injection":
        return Finding(
            "high",
            power,
            f"In {place}, text written by an outsider (such as a pull request title) "
            "is pasted into a shell command, so they can run their own commands.",
            _INJECTION_FIX,
        )

    if kind == "hidden":
        return Finding(
            "high",
            power,
            f"In {place}, a command decodes hidden text and runs it, "
            "so a reviewer cannot see what it does.",
            "Write the command in plain text so reviewers can read it.",
        )

    if kind == "runner":
        return Finding(
            "medium",
            power,
            f"In {place}, now runs on the project's own machine.",
            "Do not use self-hosted machines in workflows that outsiders can start.",
        )

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
                    f.fix
                    or "Make sure this address is meant to receive data, or move the secret "
                    "to a job that does not contact it.",
                )
        elif p.kind == "secret" and p.where in jobs_with_new_network:
            f = Finding("high", p, f.message, f.fix)
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
    place = _place(power.where)

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
                pin_fix(power.name),
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
    if (
        power.kind in ("secret", "network", "runner", "injection", "hidden", "local", "container")
        and same_power_existed
    ):
        return Finding(
            "low",
            power,
            f"Already present in this workflow; now also in {place}: {power.name}.",
        )
    return None


def _is_pipedelta(power: Power) -> bool:
    return power.kind == "action" and action_name(power.name).endswith("/pipedelta")


def _apply_trust(findings: list[Finding], trust: Trust) -> list[Finding]:
    """Lower the level of findings about actions and addresses the project trusts.

    The trust list is read from the target branch, never from the change being
    reviewed, so a pull request cannot trust its own additions.
    """
    out = []
    for f in findings:
        p = f.power
        trusted = (p.kind == "action" and trust.trusts_action(p.name)) or (
            p.kind == "network" and trust.trusts_host(p.name)
        )
        if trusted and f.level != "low":
            f = Finding("low", p, f.message + " (Trusted in .pipedelta.yml.)")
        out.append(f)
    return out


def compare(
    before_text: str | None, after_text: str | None, trust: Trust | None = None
) -> list[Finding]:
    """List the powers gained going from the old file to the new file.

    None means the file did not exist on that side.
    """
    before = extract_powers(before_text) if before_text else set()
    after = extract_powers(after_text) if after_text else set()
    if trust is not None:
        # A trusted address does not make a secret in the same job look stolen.
        after_for_combine = {
            p for p in after if not (p.kind == "network" and trust.trusts_host(p.name))
        }
    else:
        after_for_combine = after
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
    if trust is not None:
        truly_new = {
            p for p in truly_new if not (p.kind == "network" and trust.trusts_host(p.name))
        }
    findings = _combine(findings, truly_new, after_for_combine)
    if any(_is_pipedelta(p) for p in before) and not any(_is_pipedelta(p) for p in after):
        findings.append(_explain(Power("guard", "PipeDelta check removed"), after))
    if trust is not None:
        findings = _apply_trust(findings, trust)
    findings.sort(key=lambda f: (-LEVELS.index(f.level), f.power))
    return findings


def overall(findings: list[Finding]) -> str:
    if not findings:
        return "none"
    return max((f.level for f in findings), key=LEVELS.index)


def compare_trust(before_text: str | None, after_text: str | None) -> list[Finding]:
    """Report entries a change adds to the trust list.

    They do not lower the findings of the same change (the list is read from
    the target branch), but a reviewer should know the list is being widened.
    """
    before, after = parse_trust(before_text), parse_trust(after_text)
    findings = []
    for entry in sorted(set(after.actions) - set(before.actions)):
        findings.append(
            Finding(
                "medium",
                Power("trust", clean(entry), "config"),
                f"Adds {entry} to the trusted actions in .pipedelta.yml. From the next "
                "change on, PipeDelta will not block it.",
            )
        )
    for entry in sorted(set(after.hosts) - set(before.hosts)):
        findings.append(
            Finding(
                "medium",
                Power("trust", clean(entry), "config"),
                f"Adds {entry} to the trusted addresses in .pipedelta.yml. From the next "
                "change on, sending secrets there will not be blocked.",
            )
        )
    return findings
