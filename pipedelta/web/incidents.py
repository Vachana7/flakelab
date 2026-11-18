"""Real supply-chain incidents, rebuilt as the workflow change each one made.

The files come from the replay benchmark (evaluation/replay in the main
branch). Each one is analysed by this app's engine when it is run; no result
is stored here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

FOLDER = Path(__file__).parent / "incidents"
_ID = re.compile(r"r\d\d-[a-z0-9-]+")


def _read(folder: Path, name: str) -> str | None:
    path = folder / name
    return path.read_text(encoding="utf-8") if path.is_file() else None


def incident_list() -> list[dict[str, Any]]:
    items = []
    for folder in sorted(p for p in FOLDER.iterdir() if p.is_dir() and _ID.fullmatch(p.name)):
        case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        case["id"] = folder.name
        case["before"] = _read(folder, "before.yml")
        case["after"] = _read(folder, "after.yml")
        # The app reads workflow files. An action's own action.yml (tj-actions)
        # needs upstream review, which is on the roadmap.
        case["runnable"] = "jobs:" in (case["after"] or "")
        items.append(case)
    return sorted(items, key=lambda c: c.get("date", ""), reverse=True)


def load_incident(incident_id: str) -> dict[str, Any] | None:
    if not _ID.fullmatch(incident_id):
        return None
    for case in incident_list():
        if case["id"] == incident_id and case["runnable"]:
            name = f"{incident_id[4:]}.yml"
            return {"name": name, "before": case["before"], "after": case["after"]}
    return None
