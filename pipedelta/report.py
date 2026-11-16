"""Turn findings into text for the terminal or Markdown for a pull request."""

from __future__ import annotations

from .delta import Finding, overall

# Hidden marker so PipeDelta can find and update its own earlier comment.
MARKER = "<!-- pipedelta-report -->"

Results = dict[str, list[Finding]]


def all_findings(results: Results) -> list[Finding]:
    return [f for findings in results.values() for f in findings]


def _label(finding: Finding) -> str:
    return "reduced" if finding.change == "reduced" else finding.level


def _headline(findings: list[Finding]) -> str:
    new = [f for f in findings if f.change != "reduced"]
    reduced = len(findings) - len(new)
    if not new:
        return f"this change gives the pipeline no new powers and reduces {reduced}."
    text = f"this change gives the pipeline {len(new)} new power(s)"
    if reduced:
        text += f" and reduces {reduced}"
    return text + f". Highest level: {overall(findings)}."


def render_text(results: Results) -> str:
    everything = all_findings(results)
    if not everything:
        return "PipeDelta: no new pipeline powers in this change.\n"
    lines = [f"PipeDelta: {_headline(everything)}\n"]
    for path, findings in results.items():
        if not findings:
            continue
        lines.append(path)
        for f in findings:
            lines.append(f"  [{_label(f).upper():7}] {f.message}")
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


def render_markdown(results: Results) -> str:
    everything = all_findings(results)
    lines = [MARKER, "## PipeDelta report", ""]
    if not results:
        lines.append("This change does not touch any workflow file.")
        return "\n".join(lines) + "\n"
    if not everything:
        lines.append("Workflow files changed, but the pipeline gained no new powers.")
        return "\n".join(lines) + "\n"
    new = [f for f in everything if f.change != "reduced"]
    reduced = len(everything) - len(new)
    if not new:
        lines.append(f"This change gives the pipeline no new powers and **reduces {reduced}**.")
    else:
        also = f" and reduces {reduced}" if reduced else ""
        lines.append(
            f"This change gives the pipeline **{len(new)} new power(s)**{also}. "
            f"Highest level: **{overall(everything)}**."
        )
    for path, findings in results.items():
        if not findings:
            continue
        safe_path = path.replace("`", "'").replace("\n", " ")
        lines += ["", f"### `{safe_path}`", "", "| Level | What changed |", "|---|---|"]
        for f in findings:
            lines.append(f"| {_label(f)} | {_cell(f.message)} |")
    lines += [
        "",
        (
            "PipeDelta reads workflow files only. It does not inspect the outside "
            "actions or scripts a workflow calls. A person should still review this change."
        ),
    ]
    return "\n".join(lines) + "\n"
