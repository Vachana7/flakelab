"""Values passed from one job to another through job outputs.

Jobs run on separate machines. GitHub gives one job a value from another in
only one way that this file follows:

    jobs:
      a:
        outputs:
          title: ${{ steps.read.outputs.title }}     # a publishes "title"
      b:
        needs: a                                      # b must list a here
        steps:
          - run: echo "${{ needs.a.outputs.title }}"  # b reads it

The question answered here: can outsider-controlled text travel along such a
link and be pasted into a command in the reading job?

Rules, each taken from GitHub's documentation and each with a test:

* ``needs`` by itself passes nothing. A link exists only where the reading
  job names an output: ``needs.<job>.outputs.<name>``.
* A job can read outputs only of jobs it lists under ``needs`` directly.
* An output that the publishing job does not define is empty.
* An output whose value contains a secret is withheld by GitHub, so a secret
  is never said to arrive in the reading job this way.

When is an output said to carry outsider text? Only when the file shows it:

1. its value names an outsider-controlled field directly, or
2. its value is the output of a ``run`` step in the same job, and that step
   has outsider text in its command or in its own ``env``, or
3. its value is an output of another needed job that carries outsider text.

Everything else (an output set by an action, by a file, by the network) is
left alone: the file does not show what is in it. Artifacts and caches are
not followed.
"""

from __future__ import annotations

from typing import Any

from . import expressions


def _lower_keys(value: Any) -> dict[str, Any]:
    """A mapping with its keys in lower case; anything else becomes {}.

    GitHub looks up names in expressions without regard to capitalisation.
    """
    if not isinstance(value, dict):
        return {}
    return {str(key).lower(): item for key, item in value.items()}


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
    """One part of a reference in lower case; None if absent or chosen at run time."""
    if index >= len(path):
        return None
    part = path[index]
    return part.lower() if part is not None else None


class JobLinks:
    """Answers questions about the job outputs of one workflow."""

    def __init__(self, jobs: Any) -> None:
        self._jobs = {name: job for name, job in _lower_keys(jobs).items() if isinstance(job, dict)}
        self._carrying: set[tuple[str, str]] = set()
        self._carrying = self._find_carrying_outputs()

    def needed_by(self, job_name: str) -> set[str]:
        """The jobs this job lists under ``needs`` (lower case)."""
        needs = self._jobs.get(job_name.lower(), {}).get("needs")
        if isinstance(needs, str):
            needs = [needs]
        if not isinstance(needs, list):
            return set()
        return {item.lower() for item in needs if isinstance(item, str)}

    # -- the publishing side ------------------------------------------------

    def _step_shows_outsider_text(self, job: dict[str, Any], step_id: str) -> bool:
        """Does the ``run`` step with this id handle outsider text?"""
        steps = job.get("steps")
        for step in steps if isinstance(steps, list) else []:
            if not isinstance(step, dict) or str(step.get("id", "")).lower() != step_id:
                continue
            run = step.get("run")
            if not isinstance(run, str):
                return False  # an action: its outputs cannot be read from this file
            seen_by_step = [run, *_texts(step.get("env"))]
            return any(expressions.has_untrusted_value(text) for text in seen_by_step)
        return False

    def _find_carrying_outputs(self) -> set[tuple[str, str]]:
        """Every (job, output) that can hold outsider text.

        First the outputs that show it themselves (rules 1 and 2 at the top of
        this file). Then rule 3 is applied again and again, each round adding
        outputs that pass on one already found, until a round adds nothing.
        Each output is read once, and jobs that need each other in a circle
        simply stop adding.
        """
        carrying: set[tuple[str, str]] = set()
        passed_on: dict[tuple[str, str], list[expressions.Path]] = {}
        for job_name, job in self._jobs.items():
            for output, value in _lower_keys(job.get("outputs")).items():
                if not isinstance(value, str):
                    continue
                paths = expressions.pasted_references(value)
                shows_it = any(
                    expressions.is_untrusted(path)
                    or (
                        _part(path, 0) == "steps"
                        and _part(path, 2) == "outputs"
                        and self._step_shows_outsider_text(job, _part(path, 1) or "")
                    )
                    for path in paths
                )
                if shows_it:
                    carrying.add((job_name, output))
                else:
                    passed_on[(job_name, output)] = [p for p in paths if _part(p, 0) == "needs"]

        self._carrying = carrying  # _reads_outsider_output looks here
        added = True
        while added:
            added = False
            for (job_name, output), paths in list(passed_on.items()):
                if any(self._reads_outsider_output(path, job_name) for path in paths):
                    carrying.add((job_name, output))
                    del passed_on[(job_name, output)]
                    added = True
        return carrying

    def carries_outsider_text(self, job_name: str, output: str | None) -> bool:
        """Can this output of this job hold outsider text? ``output=None`` means any of them."""
        job_name = job_name.lower()
        if output is None:
            return any(job == job_name for job, _ in self._carrying)
        return (job_name, output.lower()) in self._carrying

    # -- the reading side ---------------------------------------------------

    def _reads_outsider_output(self, path: expressions.Path, job_name: str) -> bool:
        """Is this reference a needed job's output that can hold outsider text?

        Accepted shapes: ``needs.a.outputs.title``, ``needs.a.outputs`` and
        ``needs.a`` (all outputs of a), ``needs`` (everything needed).
        ``needs.a.result`` is not an output.
        """
        if _part(path, 0) != "needs":
            return False
        if len(path) > 2 and _part(path, 2) != "outputs":
            return False
        needed = self.needed_by(job_name)
        source = _part(path, 1)
        if len(path) > 1 and source is not None and source != "*":
            sources = {source} & needed  # a job not listed under needs gives nothing
        else:
            sources = needed  # all of them, or chosen at run time
        output = path[3] if len(path) > 3 else None
        if output == "*":
            output = None
        return any(self.carries_outsider_text(s, output) for s in sources)

    def pastes_outsider_output(self, text: str, job_name: str) -> bool:
        """Does this command paste in a needed job's output that can hold outsider text?"""
        return any(
            self._reads_outsider_output(path, job_name.lower())
            for path in expressions.pasted_references(text)
        )
