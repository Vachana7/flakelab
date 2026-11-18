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


_SARIF_LEVEL = {"high": "error", "medium": "warning", "low": "note"}
_RULES = {
    "trigger": "Runs on a new trigger",
    "permission": "Pipeline token gains a permission",
    "secret": "Can read a new secret",
    "action": "Runs new outside code",
    "network": "Contacts a new address",
    "injection": "Outsider text reaches a shell command",
    "hidden": "Runs hidden (encoded) commands",
    "runner": "Runs on a self-hosted machine",
    "local": "Runs a repository action",
    "container": "Uses a new container image",
    "code": "Runs code PipeDelta cannot read",
    "guard": "PipeDelta check removed",
    "trust": "Trust list widened",
    "memory": "Reads the runner's memory",
    "selfmod": "Can change, start or approve workflows",
    "cover": "Deletes runs or rewrites history",
    "cache": "Shares a build cache",
    "zizmor": "New zizmor finding",
}


def render_sarif(results: Results) -> str:
    """SARIF 2.1.0, so findings show in GitHub's Security tab (code scanning).

    Upload it with github/codeql-action/upload-sarif. PipeDelta does not track
    line numbers, so each result points at line 1 of its file. Low-level notes
    (version bumps, GitHub's own actions) are left out: code scanning turns every
    result into an alert and a review comment, and those would bury the real ones.
    """
    import hashlib
    import json

    from . import __version__

    kept = {path: [f for f in fs if f.level != "low"] for path, fs in results.items()}
    kinds = sorted({f.power.kind for f in all_findings(kept)})
    rules = [
        {
            "id": f"pipedelta/{kind}",
            "name": kind,
            "shortDescription": {"text": _RULES.get(kind, kind)},
            "helpUri": "https://github.com/Vachana7/pipedelta#readme",
        }
        for kind in kinds
    ]
    out = []
    for path, findings in kept.items():
        for f in findings:
            text = f.message + (f" Fix: {f.fix}" if f.fix else "")
            key = f"{path}|{f.power.kind}|{f.power.name}|{f.power.where}"
            out.append(
                {
                    "ruleId": f"pipedelta/{f.power.kind}",
                    "ruleIndex": kinds.index(f.power.kind),
                    "level": _SARIF_LEVEL.get(f.level, "note"),
                    "message": {"text": text},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": path},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                    "partialFingerprints": {
                        "pipedelta/v1": hashlib.sha256(key.encode()).hexdigest()[:32]
                    },
                    "properties": {
                        "security-severity": {"high": "8.0", "medium": "5.0"}.get(f.level, "2.0")
                    },
                }
            )
    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "PipeDelta",
                            "version": __version__,
                            "informationUri": "https://github.com/Vachana7/pipedelta",
                            "rules": rules,
                        }
                    },
                    "results": out,
                }
            ],
        },
        indent=2,
    )
