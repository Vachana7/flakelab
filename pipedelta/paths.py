"""Attack paths inside one job, and which of them a change makes possible.

A path is a pair of things held by the SAME job that are dangerous together:

  a way in or a way out          +   something worth having
  ------------------------------     ------------------------
  an outside address (way out)       a stored secret
  outsider text in a command         a token that can write
  unpinned outside code
  decoded hidden commands
  the project's own machine

A path is identified by what it is made of (which secret, which address),
never by the job's name. So renaming or reordering jobs changes nothing,
and a path counts as new only if that exact pairing existed in no job before.

This states what the file makes possible. It does not prove that a secret is
actually sent anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .jobs import JobFacts, job_facts

# A member of a path: (kind of power, its name; "" when the kind has no name).
Member = tuple[str, str]


@dataclass(frozen=True)
class AttackPath:
    rule: str  # short name of the rule that produced it
    level: str  # "medium" or "high"
    first: Member  # the way in or out
    second: Member  # the sensitive thing
    reason: str  # one sentence fragment for the report
    jobs: tuple[str, ...] = field(default=(), compare=False)  # where it was found


def holds(job: JobFacts, member: Member) -> bool:
    """Does this job hold this part of a path?"""
    kind, name = member
    if kind == "secret":
        return name in job.secrets
    if kind == "network":
        return name in job.hosts
    if kind == "action":
        return name in job.unpinned
    if kind == "write":
        return name in job.write_scopes
    return {"injection": job.injection, "hidden": job.hidden, "runner": job.self_hosted}[kind]


def _job_paths(job: JobFacts) -> list[AttackPath]:
    found: list[AttackPath] = []
    for secret in sorted(job.secrets):
        s: Member = ("secret", secret)
        for host in sorted(job.hosts):
            found.append(
                AttackPath(
                    "secret can be sent out",
                    "high",
                    ("network", host),
                    s,
                    f"a command in the same job contacts {host}, so the secret {secret} "
                    "could be sent there",
                )
            )
        if job.injection:
            found.append(
                AttackPath(
                    "outsider commands can read a secret",
                    "high",
                    ("injection", ""),
                    s,
                    "the same job pastes outsider-controlled text into a command, so an "
                    f"outsider's commands could read the secret {secret}",
                )
            )
        if job.hidden:
            found.append(
                AttackPath(
                    "hidden commands can read a secret",
                    "high",
                    ("hidden", ""),
                    s,
                    "the same job decodes hidden text and runs it, and those commands "
                    f"could read the secret {secret}",
                )
            )
        for tool in sorted(job.unpinned):
            found.append(
                AttackPath(
                    "outside code can read a secret",
                    "high",
                    ("action", tool),
                    s,
                    f"the same job runs outside code {tool} that is not locked to a commit, "
                    f"and that code could read the secret {secret}",
                )
            )
        if job.self_hosted:
            found.append(
                AttackPath(
                    "secret on the project's own machine",
                    "medium",
                    ("runner", ""),
                    s,
                    f"the secret {secret} is now used on the project's own machine, "
                    "which keeps its state between runs",
                )
            )
    for scope in sorted(job.write_scopes):
        w: Member = ("write", scope)
        if job.injection:
            found.append(
                AttackPath(
                    "outsider commands run with a write token",
                    "high",
                    ("injection", ""),
                    w,
                    "the same job pastes outsider-controlled text into a command and its "
                    f"token can change {scope}",
                )
            )
        for tool in sorted(job.unpinned):
            found.append(
                AttackPath(
                    "outside code runs with a write token",
                    "high",
                    ("action", tool),
                    w,
                    f"outside code {tool}, not locked to a commit, runs in a job whose "
                    f"token can change {scope}",
                )
            )
    return found


def paths_in(text: str | None) -> list[AttackPath]:
    """Every path in one workflow file, each listed once with the jobs that hold it."""
    holders: dict[AttackPath, list[str]] = {}
    for job in job_facts(text).values():
        for path in _job_paths(job):
            holders.setdefault(path, []).append(job.name)
    return [
        AttackPath(p.rule, p.level, p.first, p.second, p.reason, tuple(jobs))
        for p, jobs in holders.items()
    ]


def new_paths(before_text: str | None, after_text: str | None) -> list[AttackPath]:
    """Paths possible after the change that were possible in no job before it."""
    existed = set(paths_in(before_text))
    return [p for p in paths_in(after_text) if p not in existed]
