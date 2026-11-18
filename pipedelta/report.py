"""Turn findings into text for the terminal or Markdown for a pull request."""

from __future__ import annotations

from .delta import Finding, overall

# Hidden marker so PipeDelta can find and update its own earlier comment.
MARKER = "<!-- pipedelta-report -->"

Results = dict[str, list[Finding]]


def all_findings(results: Results) -> list[Finding]:
    return [f for findings in results.values() for f in findings]


def render_text(results: Results) -> str:
    everything = all_findings(results)
    if not everything:
        return "PipeDelta: no new pipeline powers in this change.\n"
    lines = [
        (
            f"PipeDelta: this change gives the pipeline {len(everything)} new power(s). "
            f"Highest level: {overall(everything)}.\n"
        )
    ]
    for path, findings in results.items():
        if not findings:
            continue
        lines.append(path)
        for f in findings:
            lines.append(f"  [{f.level.upper():6}] {f.message}")
            if f.fix and f.level != "low":
                lines.append(f"           fix: {f.fix}")
        lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    """Make text safe to place inside a Markdown table cell.

    Parts of the sentence (job names, action names) come from the change being
    reviewed. Without this, a job named like a link or an @mention would
    become a real link or notify people from the comment.
    """
    text = text.replace("\\", "\\\\").replace("\n", " ")
    for char in "|`*_[]<>~#!":
        text = text.replace(char, "\\" + char)
    text = text.replace("@", "@\u200b")
    return text.replace("://", ":\u200b//")


_BADGES = {"high": "🔴 high", "medium": "🟠 medium", "low": "⚪ low"}


def _badge(level: str) -> str:
    return _BADGES.get(level, level)


def _code_cell(text: str) -> str:
    """A fix suggestion: plain words escaped, `code` kept as code."""
    parts = text.split("`")
    out = []
    for i, part in enumerate(parts):
        if i % 2:  # inside backticks: only keep it on one line and out of the table
            out.append("`" + part.replace("|", "\\|").replace("\n", " ").replace("`", "'") + "`")
        else:
            out.append(_cell(part))
    return "".join(out)


def render_json(results: Results) -> str:
    """Machine-readable output, for dashboards and other tools."""
    import json

    everything = all_findings(results)
    return json.dumps(
        {
            "level": overall(everything),
            "count": len(everything),
            "files": {
                path: [
                    {
                        "level": f.level,
                        "kind": f.power.kind,
                        "name": f.power.name,
                        "job": f.power.where,
                        "message": f.message,
                        "fix": f.fix,
                    }
                    for f in findings
                ]
                for path, findings in results.items()
            },
        },
        indent=2,
    )


def render_markdown(results: Results) -> str:
    everything = all_findings(results)
    lines = [MARKER, "## PipeDelta report", ""]
    if not results:
        lines.append("This change does not touch any workflow file.")
        return "\n".join(lines) + "\n"
    if not everything:
        lines.append("Workflow files changed, but the pipeline gained no new powers.")
        return "\n".join(lines) + "\n"
    lines.append(
        f"This change gives the pipeline **{len(everything)} new power(s)**. "
        f"Highest level: **{overall(everything)}**."
    )
    for path, findings in results.items():
        if not findings:
            continue
        safe_path = path.replace("`", "'").replace("\n", " ")
        lines += [
            "",
            f"### `{safe_path}`",
            "",
            "| Level | New power | How to fix |",
            "|---|---|---|",
        ]
        for f in findings:
            fix = _code_cell(f.fix) if f.fix and f.level != "low" else ""
            lines.append(f"| {_badge(f.level)} | {_cell(f.message)} | {fix} |")
    lines += [
        "",
        (
            "PipeDelta reads workflow files and the actions stored in this repository. "
            "It does not inspect outside actions or the scripts a step runs. "
            "A person should still review this change."
        ),
    ]
    return "\n".join(lines) + "\n"
