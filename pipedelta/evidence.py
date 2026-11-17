"""Evidence for every finding: where it is, what changed, how sure we are, what to do.

``compare()`` (delta.py) decides WHAT changed. This module adds the facts a
reviewer needs to check it in the file:

* file, job, step and line (counted from 1), from PyYAML's source positions;
* the previous and the new value;
* a few lines of the file around it;
* severity, confidence and precision (see docs/EVIDENCE.md);
* why it matters and what to do about it.

Nothing here decides a level. It reads the findings ``compare()`` returned and
places them. If a finding cannot be placed, it is still reported, with a
lower ``precision``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import expressions
from .delta import Finding, compare
from .expressions import ALL_SECRETS
from .permissions import job_tokens
from .powers import (
    BUILT_IN_TOKEN,
    FIRST_PARTY,
    HIDDEN_RE,
    INJECTION_FROM_JOB,
    INJECTION_FROM_STEP,
    RISKY_TRIGGERS,
    action_name,
    action_owner,
    extract_powers,
    is_pinned,
)
from .stepflows import flows_in
from .text import CONTROL_RE

CONTEXT_LINES = 2  # lines shown above and below the finding
MAX_LINE = 200  # characters kept per line of the snippet
ALL_SECRETS_NAMES = {ALL_SECRETS}


# ---- the result ---------------------------------------------------------------------


@dataclass(frozen=True)
class SnippetLine:
    number: int  # counted from 1
    text: str
    hit: bool


@dataclass(frozen=True)
class Evidence:
    id: str
    severity: str  # low, medium, high
    confidence: str  # low, medium, high
    change: str  # gained, reduced, improved, unknown
    kind: str  # trigger, permission, secret, action, network, injection, runner, hidden
    name: str  # the specific thing: a secret name, a host, "contents: write"
    title: str
    message: str  # the sentence compare() produced
    file: str
    job: str | None
    jobs: tuple[str, ...]
    step: int | None  # counted from 1
    step_label: str | None
    line: int | None  # counted from 1
    precision: str  # "line", "job" or "file"
    side: str  # "after" (the new file) or "before" (a removed power is in the old file)
    previous: str | None
    new: str | None
    consequence: str
    remediation: str
    snippet: tuple[SnippetLine, ...] = field(default=())

    def snippet_text(self) -> str:
        return "\n".join(s.text for s in self.snippet)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "confidence": self.confidence,
            "change": self.change,
            "kind": self.kind,
            "name": self.name,
            "title": self.title,
            "message": self.message,
            "file": self.file,
            "job": self.job,
            "jobs": list(self.jobs),
            "step": self.step,
            "step_label": self.step_label,
            "line": self.line,
            "precision": self.precision,
            "side": self.side,
            "previous": self.previous,
            "new": self.new,
            "consequence": self.consequence,
            "remediation": self.remediation,
            "snippet": [{"number": s.number, "text": s.text, "hit": s.hit} for s in self.snippet],
        }


# ---- reading the file's layout ------------------------------------------------------


@dataclass(frozen=True)
class Span:
    first: int  # 0-based, inclusive
    last: int


@dataclass(frozen=True)
class StepSite:
    span: Span
    label: str


@dataclass
class JobSite:
    key_line: int
    span: Span
    fields: dict[str, tuple[int, Span]] = field(default_factory=dict)
    steps: list[StepSite] = field(default_factory=list)


def _span(node: yaml.Node, lines: list[str]) -> Span:
    """The lines a node covers (0-based, inclusive).

    PyYAML ends a block where the NEXT token starts. If only blanks come before
    that point on its line, the next token begins a new line and this node
    ended on the line before.
    """
    first = node.start_mark.line
    last = node.end_mark.line
    if last > first and last < len(lines) and not lines[last][: node.end_mark.column].strip():
        last -= 1
    return Span(first, min(last, max(len(lines) - 1, first)))


def _key(node: yaml.Node) -> str | None:
    return str(node.value) if isinstance(node, yaml.ScalarNode) else None


def _mapping(node: yaml.Node | None) -> list[tuple[str, yaml.Node, yaml.Node]]:
    if not isinstance(node, yaml.MappingNode):
        return []
    items = []
    for key_node, value_node in node.value:
        key = _key(key_node)
        if key is not None:
            items.append((key, key_node, value_node))
    return items


def _clip(text: str) -> str:
    """Make one line of the file safe and short enough to show."""
    text = CONTROL_RE.sub("", text.replace("\t", "  ")).rstrip()
    return text if len(text) <= MAX_LINE else text[: MAX_LINE - 1] + "…"


def _short(text: str, limit: int = 60) -> str:
    text = CONTROL_RE.sub("", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SourceMap:
    """Where the top-level keys, jobs and steps of one workflow file are."""

    def __init__(self, text: str | None) -> None:
        self.lines = (text or "").splitlines()
        self.top: dict[str, tuple[int, Span]] = {}
        self.jobs: dict[str, JobSite] = {}
        try:
            root = yaml.compose(text or "", Loader=yaml.SafeLoader)
        except yaml.YAMLError:
            return
        for key, key_node, value_node in _mapping(root):
            self.top[key] = (key_node.start_mark.line, _span(value_node, self.lines))
            if key == "jobs":
                self._read_jobs(value_node)

    def _read_jobs(self, jobs_node: yaml.Node) -> None:
        for name, key_node, job_node in _mapping(jobs_node):
            site = JobSite(
                key_node.start_mark.line,
                Span(key_node.start_mark.line, _span(job_node, self.lines).last),
            )
            for field_name, field_key, field_value in _mapping(job_node):
                site.fields[field_name] = (
                    field_key.start_mark.line,
                    _span(field_value, self.lines),
                )
                if field_name == "steps" and isinstance(field_value, yaml.SequenceNode):
                    for step_node in field_value.value:
                        site.steps.append(
                            StepSite(_span(step_node, self.lines), self._label(step_node))
                        )
            self.jobs[_short(name, 100)] = site

    @staticmethod
    def _label(step_node: yaml.Node) -> str:
        fields = {k: v for k, _, v in _mapping(step_node)}
        for name in ("name", "uses"):
            value = fields.get(name)
            if isinstance(value, yaml.ScalarNode) and str(value.value).strip():
                return _short(str(value.value))
        run = fields.get("run")
        if isinstance(run, yaml.ScalarNode):
            first = next((ln for ln in str(run.value).splitlines() if ln.strip()), "")
            return _short("run: " + first)
        return "step"

    def find(self, span: Span, test: Callable[[str], object]) -> int | None:
        """The first line (0-based) in the span for which ``test`` is true."""
        for number in range(span.first, min(span.last, len(self.lines) - 1) + 1):
            if test(self.lines[number]):
                return number
        return None

    def step_at(self, job: JobSite, line: int) -> int | None:
        for index, step in enumerate(job.steps, start=1):
            if step.span.first <= line <= step.span.last:
                return index
        return None


# ---- placing one finding --------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    job: str | None
    jobs: tuple[str, ...]
    step: int | None
    step_label: str | None
    line: int | None  # 0-based here; 1-based in Evidence
    precision: str


def _secret_test(name: str) -> Callable[[str], object]:
    if name in ALL_SECRETS_NAMES:
        return lambda line: "secrets" in line.lower() and ("tojson" in line.lower() or "*" in line)
    if name == "(all secrets, inherited)":
        return lambda line: re.search(r"secrets\s*:\s*inherit", line) is not None
    if name.startswith("(a secret chosen"):
        return lambda line: re.search(r"secrets\s*\[", line, re.IGNORECASE) is not None
    pattern = re.compile(
        rf"secrets\s*(?:\.\s*{re.escape(name)}\b|\[\s*['\"]{re.escape(name)}['\"]\s*\])",
        re.IGNORECASE,
    )
    return lambda line: pattern.search(line) is not None


def _in_steps(smap: SourceMap, job: JobSite, test: Callable[[str], object]) -> int | None:
    for step in job.steps:
        found = smap.find(step.span, test)
        if found is not None:
            return found
    return None


def _job_names(where: str, smap: SourceMap) -> tuple[str, ...]:
    if where == "workflow":
        return ()
    if where in smap.jobs:
        return (where,)
    return tuple(part.strip() for part in where.split(",") if part.strip())


def _place(finding: Finding, smap: SourceMap, flows: dict[str, list[Any]]) -> Placed:
    power = finding.power
    kind, name = power.kind, power.name
    jobs = _job_names(power.where, smap)
    job_name = jobs[0] if jobs else None
    job = smap.jobs.get(job_name) if job_name else None

    line: int | None = None
    exact = False

    if kind == "trigger":
        entry = smap.top.get("on")
        if entry is not None:
            hit = smap.find(
                entry[1], lambda ln: re.search(rf"\b{re.escape(name)}\b", ln) is not None
            )
            line, exact = (hit, True) if hit is not None else (entry[0], False)

    elif kind == "permission":
        scope = name.split(":", 1)[0].strip()
        block = job.fields.get("permissions") if job else None
        if block is None:
            block = smap.top.get("permissions")
        if block is not None:
            hit = smap.find(
                block[1], lambda ln: re.search(rf"\b{re.escape(scope)}\b", ln) is not None
            )
            line, exact = (hit, True) if hit is not None else (block[0], False)

    elif job is not None:
        if kind == "secret":
            test = _secret_test(name)
            hit = smap.find(job.span, test)
            line, exact = (hit, hit is not None)
        elif kind == "action":
            pattern = re.compile(rf"uses\s*:\s*['\"]?{re.escape(name)}", re.IGNORECASE)
            hit = smap.find(job.span, lambda ln: pattern.search(ln) is not None)
            line, exact = (hit, hit is not None)
        elif kind == "network":
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            hit = _in_steps(smap, job, lambda ln: pattern.search(ln) is not None)
            line, exact = (hit, hit is not None)
        elif kind == "hidden":
            hit = _in_steps(smap, job, lambda ln: HIDDEN_RE.search(ln) is not None)
            line, exact = (hit, hit is not None)
        elif kind == "runner":
            entry = job.fields.get("runs-on")
            if entry is not None:
                hit = smap.find(entry[1], lambda ln: "self-hosted" in ln)
                line, exact = (hit, True) if hit is not None else (entry[0], False)
        elif kind == "injection":
            line, exact = _place_injection(finding, smap, job, jobs[0], flows)

    if line is None and job is not None:
        line, exact = job.key_line, False
    if line is None:
        return Placed(job_name, jobs, None, None, None, "file")

    step = smap.step_at(job, line) if job is not None else None
    label = job.steps[step - 1].label if job is not None and step is not None else None
    return Placed(job_name, jobs, step, label, line, "line" if exact else "job")


def _place_injection(
    finding: Finding, smap: SourceMap, job: JobSite, job_name: str, flows: dict[str, list[Any]]
) -> tuple[int | None, bool]:
    name = finding.power.name
    if name == INJECTION_FROM_STEP:
        for flow in flows.get(job_name, []):
            if flow.sink_position <= len(job.steps):
                step = job.steps[flow.sink_position - 1]
                pattern = re.compile(re.escape(flow.reference), re.IGNORECASE)
                hit = smap.find(step.span, pattern.search)
                return (hit, True) if hit is not None else (step.span.first, False)
        return None, False
    if name == INJECTION_FROM_JOB:
        hit = _in_steps(smap, job, lambda ln: "${{" in ln and "needs" in ln.lower())
        return hit, hit is not None
    hit = _in_steps(smap, job, lambda ln: "${{" in ln and expressions.has_untrusted_value(ln))
    return hit, hit is not None


# ---- values, wording ----------------------------------------------------------------------


def _confidence(finding: Finding) -> str:
    if finding.change == "unknown":
        return "low"  # the file does not say
    if finding.power.kind == "injection" and finding.power.name in (
        INJECTION_FROM_STEP,
        INJECTION_FROM_JOB,
    ):
        return "medium"  # inferred by a rule, not written in the file
    return "high"


def _describe(finding: Finding) -> tuple[str, str, str]:
    """Title, consequence, remediation. Plain sentences; nothing is guessed."""
    power = finding.power
    kind, name = power.kind, power.name

    if finding.change in ("reduced", "improved"):
        verb = "Removed" if finding.change == "reduced" else "Safer"
        what = {
            "reduced": "The pipeline can do less than before.",
            "improved": "The same power is now held more safely.",
        }[finding.change]
        return f"{verb}: {_subject(finding)}", what, "No action needed."

    if kind == "trigger":
        if name in RISKY_TRIGGERS:
            return (
                f"Runs on {name}",
                (
                    f"{name} starts the pipeline with the project's secrets and a token that can "
                    "write, even when the change comes from someone outside the project."
                ),
                (
                    f"Use pull_request unless secrets are really needed. If {name} must stay, never "
                    "check out or run the pull request's code in it, and limit its permissions."
                ),
            )
        return (
            f"Also runs on {name}",
            "The pipeline now starts in one more situation.",
            "Check that this trigger is intended.",
        )

    if kind == "secret":
        if name == BUILT_IN_TOKEN:
            return (
                "Passes the built-in token to a step",
                "The step can use the token for whatever the permissions allow.",
                "Keep the permissions: block at the least access the job needs.",
            )
        if name in ALL_SECRETS_NAMES or name.startswith("(all secrets"):
            return (
                "Can read every secret",
                "Every command in this job can read every secret of the repository.",
                "Name only the secrets the job needs instead of passing all of them.",
            )
        return (
            f"Reads secret {name}",
            (
                f"Every command in this job can read {name}. Code that runs here, including "
                "outside actions, could send it somewhere else."
            ),
            (
                "Give the secret only to the one step that needs it (env: on that step), and keep "
                "unpinned outside code out of this job."
            ),
        )

    if kind == "action":
        tool = action_name(name)
        if action_owner(name) in FIRST_PARTY:
            return (
                f"Runs GitHub's {tool}",
                "GitHub's own action runs in the pipeline.",
                "Check the version is the one intended.",
            )
        if is_pinned(name):
            return (
                f"Runs outside action {tool}",
                (
                    "Outside code runs in the pipeline. It is locked to one commit, so it cannot "
                    "change without a visible edit."
                ),
                "Review the code at that commit, and update the commit deliberately.",
            )
        return (
            f"Runs unpinned action {tool}",
            (
                "The author of the action can change what this version does at any time, and it "
                "runs inside your pipeline."
            ),
            (
                "Replace the version tag with the full 40-character commit ID you reviewed, and "
                "keep the tag as a comment."
            ),
        )

    if kind == "network":
        return (
            f"Contacts {name}",
            (
                f"A command in this job sends or fetches data at {name}. If the job can read "
                "secrets, they could be sent there."
            ),
            (
                "Check that the destination is trusted. If the job holds secrets, remove or "
                "restrict the call."
            ),
        )

    if kind == "injection":
        source = {
            INJECTION_FROM_STEP: "an earlier step's output",
            INJECTION_FROM_JOB: "another job's output",
        }.get(name, "a pull request, issue or branch name")
        return (
            "Outsider text pasted into a command",
            (
                f"Text that someone outside the project can write (from {source}) is pasted into a "
                "shell command before the shell starts, so they can run their own commands with this "
                "job's secrets and token."
            ),
            (
                'Pass the value through an env: variable and use "$NAME" in the script, so the '
                "shell treats it as data and not as commands."
            ),
        )

    if kind == "runner":
        return (
            "Runs on a self-hosted machine",
            (
                "A machine the project owns keeps its files and credentials between runs, so one "
                "bad run can affect later ones."
            ),
            (
                "Use GitHub-hosted runners for changes from outside the project, or make the "
                "self-hosted runner single-use."
            ),
        )

    if kind == "hidden":
        return (
            "Decodes hidden text and runs it",
            "A reviewer cannot read what the command does.",
            "Write the command in plain text.",
        )

    if kind == "permission":
        scope, _, level = name.partition(":")
        scope, level = scope.strip(), level.strip()
        if finding.change == "unknown":
            return (
                "Token permissions cannot be read from the file",
                "The repository's default applies, which may allow changing the repository.",
                "Write an explicit permissions: block with the least access needed.",
            )
        verb = "change" if level == "write" else "read"
        return (
            f"Token can {verb} {scope}",
            f"A step in this job can {verb} {scope} in the repository with the built-in token.",
            (
                "Set permissions: at the top of the workflow to the least access needed (for "
                "example contents: read) and grant write only to the job that needs it."
            ),
        )

    return (finding.message, "", "Review this change.")


def _subject(finding: Finding) -> str:
    power = finding.power
    if power.kind == "injection":
        return "outsider text pasted into a command"
    if power.kind == "secret":
        return f"secret {power.name}"
    if power.kind == "network":
        return f"contact with {power.name}"
    if power.kind == "runner":
        return "self-hosted machine"
    return f"{power.kind} {power.name}"


def _values(
    finding: Finding, before_text: str | None, before_powers: set[Any]
) -> tuple[str | None, str | None]:
    power = finding.power
    if finding.change == "reduced":
        return _subject(finding), None
    new: str | None = _subject(finding) if power.kind != "action" else power.name
    previous: str | None = None
    if power.kind == "action":
        for old in sorted(before_powers):
            if (
                old.kind == "action"
                and action_name(old.name) == action_name(power.name)
                and old.name != power.name
            ):
                previous = old.name
                break
    elif power.kind == "permission" and before_text:
        scope = power.name.split(":", 1)[0].strip()
        tokens = job_tokens(yaml.safe_load(before_text))
        job = power.where.split(",")[0].strip()
        if job in tokens and tokens[job].known:
            previous = f"{scope}: {tokens[job].level(scope)}"
        new = power.name
    return previous, new


# ---- the entry point ----------------------------------------------------------------------


def explain(
    before_text: str | None, after_text: str | None, file: str = "workflow.yml"
) -> list[Evidence]:
    """Findings for one workflow file, each with its evidence.

    ``before_text`` is None for a new file (or when the whole file is being
    analysed on its own); ``after_text`` is None for a deleted file.
    """
    findings = compare(before_text, after_text)
    if not findings:
        return []

    safe_file = _short(file, 200)
    maps = {"after": SourceMap(after_text), "before": SourceMap(before_text)}
    flows: dict[str, list[Any]] = {}
    for flow in flows_in(after_text):
        flows.setdefault(flow.job, []).append(flow)
    before_powers = extract_powers(before_text) if before_text else set()

    result: list[Evidence] = []
    seen: set[str] = set()
    for finding in findings:
        side = "before" if finding.change == "reduced" else "after"
        smap = maps[side]
        placed = _place(finding, smap, flows if side == "after" else {})
        title, consequence, remediation = _describe(finding)
        previous, new = _values(finding, before_text, before_powers)

        snippet: tuple[SnippetLine, ...] = ()
        if placed.line is not None:
            lines = smap.lines
            low = max(0, placed.line - CONTEXT_LINES)
            high = min(len(lines) - 1, placed.line + CONTEXT_LINES)
            snippet = tuple(
                SnippetLine(n + 1, _clip(lines[n]), n == placed.line) for n in range(low, high + 1)
            )

        digest = hashlib.sha1(
            f"{safe_file}|{side}|{finding.power.kind}|{finding.power.name}|{finding.power.where}|"
            f"{finding.change}|{placed.line}".encode(errors="replace")
        ).hexdigest()[:10]
        while digest in seen:
            digest = hashlib.sha1(digest.encode()).hexdigest()[:10]
        seen.add(digest)

        result.append(
            Evidence(
                id=digest,
                severity=finding.level,
                confidence=_confidence(finding),
                change=finding.change,
                kind=finding.power.kind,
                name=finding.power.name,
                title=title,
                message=finding.message,
                file=safe_file,
                job=placed.job,
                jobs=placed.jobs,
                step=placed.step,
                step_label=placed.step_label,
                line=None if placed.line is None else placed.line + 1,
                precision=placed.precision,
                side=side,
                previous=previous,
                new=new,
                consequence=consequence,
                remediation=remediation,
                snippet=snippet,
            )
        )
    return result
