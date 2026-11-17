"""What each job holds: the unit that security reasoning is done on.

Steps in one job share a machine, a token and environment variables, so a
secret and a command in the same job can meet. Two different jobs do not
share those things. That is why facts are collected per job.

Nothing new is read from the file here. The facts are regrouped from what
``powers.py`` and ``permissions.py`` already extract.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .permissions import WRITE, job_tokens
from .powers import (
    BUILT_IN_TOKEN,
    FIRST_PARTY,
    action_name,
    action_owner,
    extract_powers,
    is_pinned,
)

ANY_SCOPE = "every scope"  # the token was given write-all


@dataclass(frozen=True)
class JobFacts:
    name: str
    secrets: frozenset[str]  # stored secrets the job can read (not the built-in token)
    hosts: frozenset[str]  # outside addresses its commands contact
    unpinned: frozenset[str]  # outside actions not locked to a commit, without version
    write_scopes: frozenset[str]  # what its token can change; empty if read-only or unknown
    injection: bool  # outsider-controlled text is pasted into a command
    hidden: bool  # decodes text and runs it
    self_hosted: bool  # runs on the project's own machine


def job_facts(text: str | None) -> dict[str, JobFacts]:
    """The facts of every job in one workflow file. None or empty text gives {}."""
    if not text:
        return {}
    powers = extract_powers(text)
    tokens = job_tokens(yaml.safe_load(text))
    # A secret set in the workflow-level env is visible to every job.
    shared = {p.name for p in powers if p.kind == "secret" and p.where == "workflow"}

    facts: dict[str, JobFacts] = {}
    for job, token in tokens.items():
        mine = [p for p in powers if p.where == job]
        secrets = {p.name for p in mine if p.kind == "secret"} | shared
        secrets.discard(BUILT_IN_TOKEN)  # the built-in token is described by write_scopes

        write: set[str] = set()
        if token.known:  # an unknown token is never assumed to be able to write
            if token.default == WRITE:
                write.add(ANY_SCOPE)
            write |= {scope for scope, level in token.scopes if level == WRITE}

        facts[job] = JobFacts(
            name=job,
            secrets=frozenset(secrets),
            hosts=frozenset(p.name for p in mine if p.kind == "network"),
            unpinned=frozenset(
                action_name(p.name)
                for p in mine
                if p.kind == "action"
                and action_owner(p.name) not in FIRST_PARTY
                and not is_pinned(p.name)
            ),
            write_scopes=frozenset(write),
            injection=any(p.kind == "injection" for p in mine),
            hidden=any(p.kind == "hidden" for p in mine),
            self_hosted=any(p.kind == "runner" for p in mine),
        )
    return facts
