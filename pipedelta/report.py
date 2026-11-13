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
        lines.append("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    """Make text safe to place inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").replace("<", "&lt;")


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
        lines += ["", f"### `{path}`", "", "| Level | New power |", "|---|---|"]
        for f in findings:
            lines.append(f"| {f.level} | {_cell(f.message)} |")
    lines += [
        "",
        (
            "PipeDelta reads workflow files only. It does not inspect the outside "
            "actions or scripts a workflow calls. A person should still review this change."
        ),
    ]
    return "\n".join(lines) + "\n"
