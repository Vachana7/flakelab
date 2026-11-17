"""Compare the powers before and after a change and explain what was gained."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import yaml

from .jobs import JobFacts, job_facts
from .paths import AttackPath, Member, holds, new_paths
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
    FIRST_PARTY,
    INJECTION_FROM_JOB,
    RISKY_TRIGGERS,
    Power,
    action_name,
    action_owner,
    extract_powers,
    is_pinned,
)

LEVELS = ["low", "medium", "high"]


@dataclass(frozen=True)
class Finding:
    level: str  # low, medium, high
    power: Power
    message: str  # one plain sentence
    # "gained": the pipeline can do something new (the default).
    # "reduced": the pipeline can do less than before. Shown, never fails the check.
    # "improved": the same power is now held more safely (an action got pinned).
    # "unknown": something changed but the file does not say in which direction.
    change: str = "gained"


# Findings with these changes are shown but never count towards the level.
NOT_COUNTED = {"reduced", "improved"}


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

    if kind == "injection" and name == INJECTION_FROM_JOB:
        return Finding(
            "high",
            power,
            f"In {place}, a command pastes in an output of another job, and that output "
            "can hold text written by an outsider (such as a pull request title), so "
            "they can run their own commands here.",
        )

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


def _member(power: Power, path: AttackPath) -> Member | None:
    """The part of the path that this power is, if it is one, in a job that holds the path."""
    if power.where not in path.jobs and power.where != "workflow":
        return None
    for member in (path.first, path.second):
        kind, name = member
        if power.kind != kind:
            continue
        if kind == "action":
            if action_name(power.name) == name:
                return member
        elif not name or power.name == name:
            return member
    return None


def _raise_for_new_paths(
    findings: list[Finding],
    gained: set[Power],
    paths: list[AttackPath],
    old_jobs: dict[str, JobFacts],
) -> list[Finding]:
    """Rate a gained power by what it now sits next to in its job.

    A secret that "already existed in the workflow" is low by itself. If it
    arrives in a job where it forms a path that existed nowhere before, the
    finding takes the path's level and says why.

    Only the part that arrived is raised. If a job already ran an unpinned
    action and now gains a secret, the secret's finding is raised; a version
    change of that action in the same commit is not, because the job held
    that part already.

    Findings are only ever raised here, never lowered, and none is added.
    """
    out: list[Finding] = []
    for f in findings:
        if f.change == "gained" and f.power in gained:
            for path in paths:
                member = _member(f.power, path)
                if member is None:
                    continue
                job_before = old_jobs.get(f.power.where)
                if job_before is not None and holds(job_before, member):
                    continue  # this job had that part before; the other part is what arrived
                if LEVELS.index(path.level) > LEVELS.index(f.level):
                    where = _place(list(path.jobs))
                    f = replace(
                        f,
                        level=path.level,
                        message=f"{f.message} New dangerous combination in {where}: {path.reason}.",
                    )
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
        tool = action_name(power.name)
        was_pinned = all(is_pinned(b.name) for b in same_tool)
        now_pinned = is_pinned(power.name)
        if was_pinned and not now_pinned:
            return Finding(
                "high",
                power,
                f"In {place}, {tool} was locked to one commit and is now "
                f"referenced as {power.name}, which its author can change at any time.",
            )
        if now_pinned and not was_pinned:
            return Finding(
                "low",
                power,
                f"In {place}, {tool} is now locked to one commit, "
                "so its author can no longer change what runs.",
                change="improved",
            )
        if now_pinned:
            # Still locked, but to other code. Not better or worse by itself.
            return Finding(
                "low",
                power,
                f"In {place}, {tool} is now locked to a different commit. "
                "Check that the new commit is the one intended.",
            )
        return Finding("low", power, f"In {place}, the version of {tool} changed to {power.name}.")

    same_power_existed = any(b.kind == power.kind and b.name == power.name for b in before)
    if power.kind in ("secret", "network", "runner", "injection", "hidden") and same_power_existed:
        return Finding(
            "low",
            power,
            f"Already present in this workflow; now also in {place}: {power.name}.",
        )
    return None


def _removal_sentence(kind: str, name: str) -> str:
    if kind == "trigger":
        return f"No longer runs on '{name}'."
    if kind == "secret":
        return f"No longer reads the secret {name}."
    if kind == "action":
        whose = "GitHub's own action" if action_owner(name) in FIRST_PARTY else "outside code"
        return f"No longer runs {whose} {name}."
    if kind == "network":
        return f"No command contacts {name} any more."
    if kind == "runner":
        return "No longer runs on the project's own machine."
    if kind == "injection" and name == INJECTION_FROM_JOB:
        return "No longer pastes another job's outsider-controlled output into a shell command."
    if kind == "injection":
        return "No longer pastes outsider-controlled text into a shell command."
    if kind == "hidden":
        return "No longer decodes hidden text and runs it."
    return f"No longer has: {kind} {name}."


def _same_power(a: Power, b: Power) -> bool:
    """Same power regardless of which job holds it. Actions match by tool, not version."""
    if a.kind != b.kind:
        return False
    if a.kind == "action":
        return action_name(a.name) == action_name(b.name)
    return a.name == b.name


def _removal_findings(before: set[Power], after: set[Power], jobs_after: set[str]) -> list[Finding]:
    """Powers that were taken away.

    Gone from the whole workflow: one finding per power.
    Gone from one job but still held by another: a finding for that job,
    unless another job newly received it (it moved) or the job no longer
    exists under that name (it was renamed). Those two are not reductions.
    """
    gone: dict[tuple[str, str], list[str]] = {}
    narrowed: list[Finding] = []
    for power in before - after:
        if power.kind == "permission":
            continue  # handled from the effective tokens
        if any(_same_power(power, other) for other in after):
            # Still in the workflow. If its job still exists and no job newly
            # received it, the power was simply taken away from that job.
            # (If another job received it, it moved; a renamed job no longer
            # exists under the old name. Neither is a reduction.)
            moved = any(_same_power(power, other) for other in after - before)
            if power.where in jobs_after and not moved:
                narrowed.append(
                    Finding(
                        "low",
                        power,
                        f"Job '{power.where}': {_removal_sentence(power.kind, power.name)} "
                        "It is still present in another job.",
                        change="reduced",
                    )
                )
            continue
        gone.setdefault((power.kind, power.name), []).append(power.where)
    return [
        Finding(
            "low",
            Power(kind, name, ", ".join(sorted(places))),
            _removal_sentence(kind, name),
            change="reduced",
        )
        for (kind, name), places in gone.items()
    ] + narrowed


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
    findings = [_permission_finding(change, jobs, held) for (change, held), jobs in grouped.items()]

    # Jobs that no longer exist. What their tokens could do is gone, unless a
    # job in the new file can do the same (which is the case after a rename).
    lost: dict[Change, list[str]] = {}
    for job, token in before.items():
        if job in after:
            continue
        for change in compare_tokens(token, NOTHING):
            if change.old == UNKNOWN:
                continue  # the file never said what this job could do
            if not _held_before(Change(change.scope, NONE, change.old, INCREASE), after.values()):
                lost.setdefault(change, []).append(job)
    for change, jobs in lost.items():
        findings.append(
            Finding(
                "low",
                Power("permission", f"{change.scope}: {change.new}", ", ".join(jobs)),
                f"The removed {_place(jobs)} had {change.scope}: {change.old}. "
                "No job has that any more.",
                change="reduced",
            )
        )
    return findings


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
    findings = _raise_for_new_paths(
        findings, gained, new_paths(before_text, after_text), job_facts(before_text)
    )
    jobs_after = set(job_tokens(yaml.safe_load(after_text))) if after_text else set()
    findings += _removal_findings(before, after, jobs_after)
    findings += _permission_findings(before_text, after_text)
    findings.sort(key=lambda f: (f.change in NOT_COUNTED, -LEVELS.index(f.level), f.power))
    return findings


def overall(findings: list[Finding]) -> str:
    """The highest level among findings that are not reductions or improvements."""
    counted = [f for f in findings if f.change not in NOT_COUNTED]
    if not counted:
        return "none"
    return max((f.level for f in counted), key=LEVELS.index)
