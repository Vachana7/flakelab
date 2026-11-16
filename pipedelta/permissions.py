"""Work out what a job's token is really allowed to do.

GitHub decides a job's permissions in this order (GitHub Docs, "Workflow
syntax for GitHub Actions", section "permissions"):

  1. If the job has its own ``permissions`` block, that block is used.
  2. Otherwise, if the workflow has a ``permissions`` block, that is used.
  3. Otherwise the repository's default applies. That default is a setting
     outside the workflow file, so PipeDelta cannot see it.

When a block names some scopes, every scope it does not name is set to "none".

Known limits of this model:

* Scope names are kept exactly as written. ``Contents`` and ``contents`` are
  treated as two different scopes, because we have not verified how GitHub
  treats capital letters in scope names.
* There is no list of valid scope names. A misspelt or brand-new scope is
  accepted and reported under the name used in the file.
* Only the file is modelled. Organisation limits, fork rules and the
  repository default are outside it.

Nothing in this file compares two versions. It only answers:
"given this workflow and this job, what does the job's token get?"
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

NONE = "none"
READ = "read"
WRITE = "write"
UNKNOWN = "unknown"  # PipeDelta cannot tell from the file

# Used to say whether a change is an increase or a reduction.
RANK = {NONE: 0, READ: 1, WRITE: 2}

# Scopes that do not have all three levels (GitHub Docs, checked 16 Nov 2026).
NO_READ_LEVEL = {"id-token", "copilot-requests"}  # only "write" or "none"
NO_WRITE_LEVEL = {"vulnerability-alerts"}  # only "read" or "none"


@dataclass(frozen=True)
class Token:
    """The effective permissions of one job.

    A token is stored as a rule plus exceptions:

    * ``default`` is the level of every scope that is not listed.
    * ``scopes`` lists the scopes that have their own level.

    Examples:
      ``write-all``            -> default "write", no exceptions
      ``{contents: read}``     -> default "none", contents is "read"
      ``{}``                   -> default "none", no exceptions
      no block anywhere        -> default "unknown" (repository default)
    """

    default: str
    scopes: tuple[tuple[str, str], ...] = ()
    # Where the answer came from: "job", "workflow" or "repository default".
    # Not part of equality: the same permissions are the same token
    # whichever block they were written in.
    source: str = field(default="", compare=False)

    @property
    def known(self) -> bool:
        """False when the token is the repository default, which the file does not show."""
        return self.default != UNKNOWN

    def level(self, scope: str) -> str:
        """The level this token has for one scope: none, read, write or unknown."""
        for name, level in self.scopes:
            if name == scope:
                return level
        if self.default == READ and scope in NO_READ_LEVEL:
            # "read-all" on a scope that has no read level. GitHub's
            # documentation does not say what happens, so we do not guess.
            return UNKNOWN
        if self.default == WRITE and scope in NO_WRITE_LEVEL:
            return READ  # documented: write-all gives this scope read
        return self.default


def _level_exists(scope: str, level: str) -> bool:
    """Is this level one that GitHub documents for this scope?"""
    if level == READ and scope in NO_READ_LEVEL:
        return False
    return not (level == WRITE and scope in NO_WRITE_LEVEL)


def repository_default() -> Token:
    """The token of a job when no ``permissions`` block applies to it."""
    return Token(default=UNKNOWN, source="repository default")


def parse_block(value: Any, source: str) -> Token:
    """Turn the value of one ``permissions:`` key into a Token.

    Anything that is not a form GitHub documents becomes "unknown" instead of
    being guessed at.
    """
    if value == "read-all":
        return Token(default=READ, source=source)
    if value == "write-all":
        return Token(default=WRITE, source=source)
    if isinstance(value, Mapping):
        listed = []
        for scope, level in value.items():
            scope = str(scope)  # kept exactly as written, including capital letters
            if not (isinstance(level, str) and level in RANK):
                level = UNKNOWN  # a typo, an expression, a list: we cannot tell
            elif not _level_exists(scope, level):
                level = UNKNOWN  # e.g. "id-token: read": GitHub documents no such level
            if level != NONE:  # "none" is already the default, so it is not an exception
                listed.append((scope, level))
        return Token(default=NONE, scopes=tuple(sorted(listed)), source=source)
    # An empty key ("permissions:" with nothing after it), a list, a number,
    # an unrecognised word: not a documented form.
    return Token(default=UNKNOWN, source=source)


def effective_token(workflow: Mapping[Any, Any], job: Mapping[Any, Any]) -> Token:
    """Apply GitHub's three-step rule and return the job's token."""
    if "permissions" in job:
        return parse_block(job["permissions"], "job")
    if "permissions" in workflow:
        return parse_block(workflow["permissions"], "workflow")
    return repository_default()
