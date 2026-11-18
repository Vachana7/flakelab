"""Downloadable reports built from a stored analysis.

Four formats: Markdown (to paste in a ticket), HTML (one file, prints well),
JSON (the full result) and SARIF 2.1.0 (what GitHub code scanning and many
other tools read). Text that came from a workflow is always escaped.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from .. import __version__

CONTENT_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "json": "application/json",
    "sarif": "application/sarif+json",
}
EXTENSIONS = {"md": "md", "html": "html", "json": "json", "sarif": "sarif"}
LEVEL_WORDS = {"high": "High", "medium": "Medium", "low": "Low", "none": "No new risk"}
SARIF_LEVEL = {"high": "error", "medium": "warning", "low": "note"}


def filename(analysis: dict[str, Any], fmt: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", analysis["title"]).strip("-").lower() or "analysis"
    return f"pipedelta-{base[:60]}-{analysis['id']}.{EXTENSIONS[fmt]}"


def _md(text: Any) -> str:
    """Escape text for Markdown (and make a table cell safe)."""
    value = str(text).replace("\\", "\\\\").replace("\n", " ")
    return re.sub(r"([`*_{}\[\]<>#|!~])", r"\\\1", value)


def _where(finding: dict[str, Any]) -> str:
    parts = [finding["file"]]
    if finding["job"]:
        parts.append(f"job {finding['job']}")
    if finding["step"]:
        parts.append(f"step {finding['step']}")
    if finding["line"]:
        parts.append(f"line {finding['line']}")
    return ", ".join(parts)


def _ordered(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    order = {"high": 0, "medium": 1, "low": 2}
    findings = [f for file in analysis["files"] for f in file["findings"]]
    return sorted(
        findings, key=lambda f: (f["change"] in ("reduced", "improved"), order[f["severity"]])
    )


def markdown(analysis: dict[str, Any]) -> str:
    s = analysis["summary"]
    out = [
        f"# PipeDelta report: {_md(analysis['title'])}",
        "",
        f"Created {analysis['created_at']} by PipeDelta {__version__}. "
        f"Overall risk: **{LEVEL_WORDS[s['level']]}**"
        + (" (the default gate would fail)." if s["would_fail"] else "."),
        "",
        (
            f"- {s['counts']['high']} high, {s['counts']['medium']} medium, "
            f"{s['counts']['low']} low across {s['files']} workflow file(s)"
        ),
        f"- {s['reduced']} power(s) removed, {s['improved']} made safer (these never raise the level)",
    ]
    refs = analysis["refs"]
    if refs.get("base") or refs.get("head"):
        base = (refs.get("base") or {}).get("label", "none")
        head = (refs.get("head") or {}).get("label", "")
        out.append(f"- Compared {base} with {head}")
    if analysis.get("pull"):
        out.append(
            f"- Pull request #{analysis['pull']['number']}: {_md(analysis['pull']['title'])}"
        )
    out.append("")
    findings = _ordered(analysis)
    if not findings:
        out.append("No findings.")
    for f in findings:
        out += [
            f"## [{f['severity'].upper()}] {_md(f['title'])}",
            "",
            f"- **Where:** {_md(_where(f))}",
            f"- **Confidence:** {f['confidence']} · **Change:** {f['change']}",
        ]
        if f["previous"]:
            out.append(f"- **Before:** {_md(f['previous'])}")
        if f["new"]:
            out.append(f"- **After:** {_md(f['new'])}")
        out += ["", _md(f["message"]), "", f"**Why it matters.** {_md(f['consequence'])}", ""]
        out.append(f"**What to do.** {_md(f['remediation'])}")
        if f["snippet"]:
            out += ["", "```yaml"]
            for line in f["snippet"]:
                mark = ">" if line["hit"] else " "
                text = line["text"].replace("```", "'''")
                out.append(f"{mark} {line['number']:>4} | {text}")
            out.append("```")
        out.append("")
    out.append(
        "_PipeDelta reads workflow files only. It does not inspect the outside actions or "
        "scripts a workflow calls. A person should still review this change._"
    )
    return "\n".join(out) + "\n"


def sarif(analysis: dict[str, Any]) -> str:
    rules: dict[str, dict[str, Any]] = {}
    results = []
    for finding in _ordered(analysis):
        if finding["change"] in ("reduced", "improved"):
            continue  # SARIF results are problems; removed powers are not
        rule_id = f"pipedelta/{finding['kind']}"
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": finding["kind"],
                "shortDescription": {"text": f"New {finding['kind']} power in a workflow"},
                "helpUri": "https://github.com/Vachana7/pipedelta/blob/main/docs/EVIDENCE.md",
            },
        )
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": SARIF_LEVEL[finding["severity"]],
            "message": {
                "text": f"{finding['title']}. {finding['message']} {finding['remediation']}"
            },
            "properties": {"confidence": finding["confidence"], "precision": finding["precision"]},
            "partialFingerprints": {"pipedeltaFinding": finding["id"]},
        }
        if finding["line"]:
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": finding["file"]},
                        "region": {"startLine": finding["line"]},
                    }
                }
            ]
        results.append(result)
    document = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "PipeDelta",
                        "version": __version__,
                        "informationUri": "https://github.com/Vachana7/pipedelta",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(document, indent=2)


_CSS = """
body{font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:#15181e;max-width:860px;margin:32px auto;padding:0 20px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:0}
.meta{color:#5b6472;margin:0 0 20px}.sum{display:flex;gap:10px;margin:0 0 24px}
.chip{border:1px solid #d6dbe3;border-radius:8px;padding:8px 14px}.chip b{display:block;font-size:22px}
.f{border:1px solid #d6dbe3;border-radius:10px;padding:14px 16px;margin:0 0 14px;break-inside:avoid}
.sev{display:inline-block;font:600 11px/1 ui-monospace,monospace;padding:4px 7px;border-radius:5px;margin-right:8px;color:#fff}
.high{background:#c8283d}.medium{background:#b86e00}.low{background:#4a6fa5}
.where{color:#5b6472;font-size:13px;margin:4px 0 8px}
pre{background:#f4f6f9;border-radius:8px;padding:10px 12px;font:12.5px/1.5 ui-monospace,monospace;overflow:auto}
pre .hit{background:#ffe9a8}
.small{color:#5b6472;font-size:13px}
@media print{body{margin:0}}
"""


def html_report(analysis: dict[str, Any]) -> str:
    e = html.escape
    s = analysis["summary"]
    parts = [
        "<!doctype html><html lang=en><meta charset=utf-8>",
        f"<title>PipeDelta report: {e(analysis['title'])}</title><style>{_CSS}</style><body>",
        (
            f"<h1>PipeDelta report</h1><p class=meta>{e(analysis['title'])} · "
            f"{e(analysis['created_at'])} · PipeDelta {e(__version__)}</p>"
        ),
        (
            f"<div class=sum><div class=chip><b>{e(LEVEL_WORDS[s['level']])}</b>overall risk</div>"
            f"<div class=chip><b>{s['counts']['high']}</b>high</div>"
            f"<div class=chip><b>{s['counts']['medium']}</b>medium</div>"
            f"<div class=chip><b>{s['counts']['low']}</b>low</div>"
            f"<div class=chip><b>{s['files']}</b>file(s)</div></div>"
        ),
    ]
    findings = _ordered(analysis)
    if not findings:
        parts.append("<p>No findings.</p>")
    for f in findings:
        parts.append(
            f"<div class=f><h2><span class='sev {e(f['severity'])}'>{e(f['severity'].upper())}</span>"
            f"{e(f['title'])}</h2><div class=where>{e(_where(f))} · confidence {e(f['confidence'])} · "
            f"{e(f['change'])}</div>"
        )
        if f["previous"] or f["new"]:
            parts.append(
                f"<p class=small>Before: {e(f['previous'] or '—')} → After: {e(f['new'] or '—')}</p>"
            )
        parts.append(
            f"<p>{e(f['message'])}</p><p><b>Why it matters.</b> {e(f['consequence'])}</p>"
            f"<p><b>What to do.</b> {e(f['remediation'])}</p>"
        )
        if f["snippet"]:
            lines = "\n".join(
                f"<span class='{'hit' if x['hit'] else ''}'>{x['number']:>4}  {e(x['text'])}</span>"
                for x in f["snippet"]
            )
            parts.append(f"<pre>{lines}</pre>")
        parts.append("</div>")
    parts.append(
        "<p class=small>PipeDelta reads workflow files only. It does not inspect the outside actions "
        "or scripts a workflow calls. A person should still review this change.</p>"
    )
    return "".join(parts)


def render(analysis: dict[str, Any], fmt: str) -> str:
    if fmt == "md":
        return markdown(analysis)
    if fmt == "html":
        return html_report(analysis)
    if fmt == "sarif":
        return sarif(analysis)
    if fmt == "json":
        return json.dumps(analysis, indent=2)
    raise ValueError(fmt)
