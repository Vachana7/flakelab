"""Run PipeDelta on every case in evaluation/attacks and write the results as JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipedelta.delta import compare, overall

ROOT = Path(__file__).parent / "attacks"


def main(out: str) -> None:
    rows = []
    for case_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        meta = json.loads((case_dir / "case.json").read_text())
        row = {
            "case": case_dir.name,
            "title": meta["title"],
            "visible": meta["workflow_change_visible"],
        }
        if meta["workflow_change_visible"]:
            before = case_dir / "before.yml"
            findings = compare(
                before.read_text() if before.exists() else None,
                (case_dir / "after.yml").read_text(),
            )
            row["level"] = overall(findings)
            row["blocked_at_default"] = row["level"] == "high"
            row["high_findings"] = sorted({f.power.kind for f in findings if f.level == "high"})
            row["all_kinds"] = sorted({f.power.kind for f in findings})
        else:
            row["level"] = "not applicable"
            row["blocked_at_default"] = False
        rows.append(row)
    Path(out).write_text(json.dumps(rows, indent=2) + "\n")
    for r in rows:
        print(f"{r['case']:34} {r['level']:15} blocked={r['blocked_at_default']}")
    visible = [r for r in rows if r["visible"]]
    print(
        f"blocked {sum(r['blocked_at_default'] for r in rows)} of {len(rows)} cases "
        f"({sum(r['blocked_at_default'] for r in visible)} of {len(visible)} where a workflow file changed)"
    )


if __name__ == "__main__":
    main(sys.argv[1])
