"""Replay real 2024-2026 CI/CD attacks (evaluation/replay) and write results as JSON.

Each case is a before/after pair rebuilt from a public write-up of a real
incident (see each case.json for the source). Unlike evaluation/attacks, these
cases were written after the rules they test were designed from the incident
reports, not from the cases, and each links to the incident it replays.

    python evaluation/run_replay.py evaluation/results/replay.json [--zizmor]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipedelta import __version__
from pipedelta.delta import compare, overall

ROOT = Path(__file__).parent / "replay"


def main(out: str, with_zizmor: bool) -> None:
    if with_zizmor:
        from pipedelta import zizmor
    rows = []
    for case_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        meta = json.loads((case_dir / "case.json").read_text())
        before_path = case_dir / "before.yml"
        before = before_path.read_text() if before_path.exists() else None
        after = (case_dir / "after.yml").read_text()
        findings = compare(before, after)
        row = {
            "case": case_dir.name,
            **meta,
            "pipedelta_version": __version__,
            "level": overall(findings),
            "blocked_at_default": overall(findings) == "high",
            "high_findings": sorted({f.power.kind for f in findings if f.level == "high"}),
        }
        if with_zizmor:
            name = "action.yml" if "jobs:" not in after else ".github/workflows/x.yml"
            new = zizmor.new_findings(before, after, name)
            row["zizmor_new_findings"] = sorted({f"{ident} ({f.level})" for ident, _, f in new})
            row["zizmor_high"] = any(f.level == "high" for _, _, f in new)
        rows.append(row)
    old = Path(out)
    if old.exists():  # keep the recorded v0.4 levels for comparison
        previous = {r["case"]: r.get("v0_4_level") for r in json.loads(old.read_text())}
        for r in rows:
            if previous.get(r["case"]):
                r["v0_4_level"] = previous[r["case"]]
    Path(out).write_text(json.dumps(rows, indent=2) + "\n")
    for r in rows:
        extra = f" zizmor_high={r.get('zizmor_high')}" if with_zizmor else ""
        print(f"{r['case']:38} {r['level']:7} blocked={r['blocked_at_default']}{extra}")
    print(f"blocked {sum(r['blocked_at_default'] for r in rows)} of {len(rows)} replayed incidents")


if __name__ == "__main__":
    main(sys.argv[1], "--zizmor" in sys.argv[2:])
