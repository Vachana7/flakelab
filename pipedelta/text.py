"""Making text from a workflow file safe to show.

Job names, scope names, action names, secret names and file paths are all
written by whoever made the change under review, who may be an attacker.
Control characters in them could recolour a terminal or fake extra lines.

Two layers use this file:

* ``clean()`` is applied where a name is read from the file.
* ``printable()`` is applied again where text is printed, so that a code
  path that forgets ``clean()`` still cannot reach the terminal.
"""

from __future__ import annotations

import re

# C0 and C1 control characters (including newline, tab and escape), and the
# invisible characters that can reorder or hide text.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069]")

MAX_NAME = 100


def printable(text: object) -> str:
    """Replace every control character with a space. Keeps the full length."""
    return CONTROL_RE.sub(" ", str(text))


def clean(text: object) -> str:
    """A name from the file, safe to print: no control characters, limited length."""
    out = printable(text).strip()
    return out if len(out) <= MAX_NAME else out[: MAX_NAME - 3] + "..."
