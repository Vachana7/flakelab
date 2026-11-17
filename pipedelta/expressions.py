"""Read GitHub Actions expressions: the text between ``${{`` and ``}}``.

Why this file exists. PipeDelta used to look for the literal text
``secrets.NAME``. GitHub accepts several other ways to write the same thing,
so a change could hide a secret from the tool by changing its spelling.

What GitHub documents ("Evaluate expressions in workflows and actions"):

* a value is reached with ``.`` (property) or ``[ ]`` (index):
  ``secrets.KEY`` and ``secrets['KEY']`` mean the same;
* strings inside an expression use single quotes; ``''`` is a literal quote.

What GitHub documents about secrets ("Secrets" reference): names "are case
insensitive when referenced" and are stored in upper case. PipeDelta
therefore reports every secret name in upper case.

What is NOT documented in the pages we read: whether the context names
themselves (``secrets``, ``github``) may be written in other capitalisation.
PipeDelta treats them as case-insensitive on purpose. If GitHub accepts
``SECRETS.KEY`` we must see it; if GitHub rejects it, the only cost is that
we report something that would not have worked.

This is a small reader for references, not an evaluator. It does not work
out what an expression's value will be.
"""

from __future__ import annotations

import re

from .text import clean

# One path = the parts of one reference, e.g. ("secrets", "KEY") or
# ("github", "event", "issue", "title"). A part is None when it is worked
# out at run time, as in secrets[matrix.name].
Path = tuple[str | None, ...]

_BODY_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)

_TOKEN_RE = re.compile(
    r"""
      (?P<string>'(?:[^']|'')*')            # 'text', with '' for a quote
    | (?P<name>[A-Za-z_][A-Za-z0-9_-]*)     # secrets, github, pull_request, my-step
    | (?P<punct>[.\[\]()*])
    | (?P<other>\S)                         # anything else: operators, numbers, commas
    """,
    re.VERBOSE,
)

ALL_SECRETS = "(every secret at once)"
RUN_TIME_SECRET = "(a secret chosen at run time)"

# Parts of the event that the person who opened a pull request, issue or
# comment can fill with their own text. Same list the tool used before.
_UNTRUSTED_EVENT_PARTS = {
    "issue",
    "pull_request",
    "comment",
    "review",
    "head_commit",
    "discussion",
}


def bodies(text: str) -> list[str]:
    """The text inside every ``${{ ... }}`` in a string.

    Limit: a ``}}`` inside a quoted string in the expression ends it early.
    """
    return _BODY_RE.findall(text)


def _tokens(body: str) -> list[tuple[str, str]]:
    return [(m.lastgroup or "other", m.group()) for m in _TOKEN_RE.finditer(body)]


def _matching_bracket(tokens: list[tuple[str, str]], start: int) -> int:
    """Index of the ``]`` that closes the ``[`` at ``start`` (or the last token)."""
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i][1] == "[":
            depth += 1
        elif tokens[i][1] == "]":
            depth -= 1
            if depth == 0:
                return i
    return len(tokens) - 1


# A reference with the positions of its first and last token in the body.
_Found = tuple[Path, int, int]


def _find(tokens: list[tuple[str, str]], offset: int = 0) -> list[_Found]:
    """Every reference in a token list, including those inside ``[ ... ]``."""
    found: list[_Found] = []
    i = 0
    while i < len(tokens):
        kind, text = tokens[i]
        is_call = i + 1 < len(tokens) and tokens[i + 1][1] == "("
        # "x).secrets" is a property of whatever the function returned,
        # not the secrets context.
        is_property = i > 0 and tokens[i - 1][1] == "."
        if kind != "name" or is_call or is_property:
            i += 1
            continue

        start = i
        parts: list[str | None] = [text]
        i += 1
        while i < len(tokens):
            here = tokens[i][1]
            after = tokens[i + 1] if i + 1 < len(tokens) else ("", "")
            if here == "." and after[0] == "name":
                parts.append(after[1])
                i += 2
            elif here == "." and after[1] == "*":
                parts.append("*")
                i += 2
            elif here == "[":
                end = _matching_bracket(tokens, i)
                inside = tokens[i + 1 : end]
                if len(inside) == 1 and inside[0][0] == "string":
                    parts.append(inside[0][1][1:-1].replace("''", "'"))
                else:
                    parts.append(None)  # decided at run time
                    found.extend(_find(inside, offset + i + 1))  # e.g. matrix.name
                i = end + 1
            else:
                break
        found.append((tuple(parts), offset + start, offset + i - 1))
    return found


def references(body: str) -> list[Path]:
    """Every reference in one expression body."""
    return [path for path, _, _ in _find(_tokens(body))]


def _is(part: str | None, word: str) -> bool:
    return part is not None and part.lower() == word


def secret_names(body: str) -> set[str]:
    """The secrets one expression body can read, with names in upper case."""
    names: set[str] = set()
    for path in references(body):
        if not _is(path[0], "secrets"):
            continue
        if len(path) == 1 or path[1] == "*":
            names.add(ALL_SECRETS)  # toJSON(secrets), secrets.*
        elif path[1] is None:
            names.add(RUN_TIME_SECRET)  # secrets[matrix.name]
        else:
            # The name can come from a quoted string, so it may hold anything.
            names.add(clean(path[1]).upper())
    return names


def is_untrusted(path: Path) -> bool:
    """Is this a value an outsider can fill with their own text?"""
    if not _is(path[0], "github") or len(path) < 2:
        return False
    if _is(path[1], "head_ref"):
        return True
    if _is(path[1], "event") and len(path) > 2 and path[2] is not None:
        return path[2].lower() in _UNTRUSTED_EVENT_PARTS
    return False


# Functions whose result is always true or false, whatever goes in.
_YES_NO_FUNCTIONS = {"contains", "startswith", "endswith"}
_COMPARISON_CHARS = {"=", "<", ">"}  # the characters of == != < > <= >=


def _enclosing_functions(tokens: list[tuple[str, str]]) -> list[frozenset[str]]:
    """For each token, the names of all function calls it sits inside."""
    result: list[frozenset[str]] = []
    stack: list[str] = []
    for i, (kind, text) in enumerate(tokens):
        if text == ")" and stack:
            stack.pop()
        result.append(frozenset(stack))
        if text == "(":
            before = tokens[i - 1] if i > 0 else ("", "")
            stack.append(before[1].lower() if before[0] == "name" else "")
    return result


def _only_compared(
    tokens: list[tuple[str, str]], start: int, end: int, inside: frozenset[str]
) -> bool:
    """Can this reference only ever contribute true/false to the result?

    Two narrow cases, chosen because they need no evaluation:

    * it sits inside contains(), startsWith() or endsWith(), which always
      return true or false;
    * it is directly next to a comparison operator, as in ``x == 'a'``.
      Comparisons bind tighter than ``&&`` and ``||``, so the reference is
      consumed by the comparison.

    Anything else is treated as able to reach the output. That errs on the
    side of reporting.
    """
    if inside & _YES_NO_FUNCTIONS:
        return True
    before = tokens[start - 1][1] if start > 0 else ""
    after = tokens[end + 1][1] if end + 1 < len(tokens) else ""
    after2 = tokens[end + 2][1] if end + 2 < len(tokens) else ""
    if before in _COMPARISON_CHARS:
        return True
    return after in _COMPARISON_CHARS or (after == "!" and after2 == "=")


def pasted_references(text: str) -> list[Path]:
    """References in the ``${{ ... }}`` of this text whose value can end up in it.

    A reference that is only compared (see ``_only_compared``) is left out,
    because it can contribute nothing but true or false.
    """
    found: list[Path] = []
    for body in bodies(text):
        tokens = _tokens(body)
        enclosing = _enclosing_functions(tokens)
        for path, start, end in _find(tokens):
            if not _only_compared(tokens, start, end, enclosing[start]):
                found.append(path)
    return found


def has_untrusted_value(text: str) -> bool:
    """Could any ``${{ ... }}`` in this text paste outsider-controlled text into it?"""
    return any(is_untrusted(path) for path in pasted_references(text))
