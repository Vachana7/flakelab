"""Example workflows that ship with the app, so it can be tried with no internet.

These are ordinary workflow files. They are analysed by the real engine each
time; nothing about the result is stored here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

FOLDER = Path(__file__).parent / "samples"

SAMPLES: list[dict[str, str]] = [
    {
        "id": "imitation-attack",
        "title": "A pull request adds a deploy job",
        "description": "A new job reads a deploy key and calls an outside address, using an outside action that is not locked to a commit.",
        "before": "before.yml",
        "after": "after-attack.yml",
    },
    {
        "id": "ordinary-change",
        "title": "An ordinary change",
        "description": "A new test step and a newer version of a GitHub action. Nothing new that can do harm.",
        "before": "before.yml",
        "after": "after-safe.yml",
    },
    {
        "id": "deploy-fixed",
        "title": "The deploy job, fixed",
        "description": "The same deploy job after locking the outside action to a commit.",
        "before": "before.yml",
        "after": "after-fixed.yml",
    },
    {
        "id": "job-output",
        "title": "Outsider text passed between jobs",
        "description": "Only the first job changes. A second job, not edited, pastes its output into a command.",
        "before": "outputs-before.yml",
        "after": "outputs-attack.yml",
    },
    {
        "id": "step-output",
        "title": "Outsider text passed between steps",
        "description": "One step now writes the pull request title to an output; a later step pastes it into a command.",
        "before": "steps-before.yml",
        "after": "steps-attack.yml",
    },
]


def sample_list() -> list[dict[str, str]]:
    return [{k: s[k] for k in ("id", "title", "description")} for s in SAMPLES]


def load_sample(sample_id: str) -> dict[str, Any] | None:
    for sample in SAMPLES:
        if sample["id"] == sample_id:
            return {
                "name": sample["after"],
                "before": (FOLDER / sample["before"]).read_text(encoding="utf-8"),
                "after": (FOLDER / sample["after"]).read_text(encoding="utf-8"),
            }
    return None
