"""Compare PipeDelta with zizmor and poutine on the same attack cases.

Usage: python evaluation/run_comparison.py OUT.json

Every tool is judged the same way: does it raise a new problem at its top
severity when going from before.yml to after.yml? (zizmor: severity High;
poutine: level error or warning, its two highest.) A tool that reports a
problem already present before the change does not get credit, because a
reviewer looking at the change would not see it as new.

zizmor runs offline. poutine needs a git repository, so each version is
committed to a throwaway repository first. Tools that are not installed are
reported as "not run".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pipedelta import zizmor
from pipedelta.delta import compare, overall

ROOT = Path(__file__).parent / "attacks"
POUTINE = shutil.which("poutine") or str(Path.home() / "go/bin/poutine")


def _version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    except OSError:
        return "not installed"
    return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else "?"


def _poutine_findings(text: str | None) -> set[tuple[str, str]]:
    if not text:
        return set()
    with tempfile.TemporaryDirectory(prefix="pd-poutine-") as tmp:
        wf = Path(tmp) / ".github/workflows/case.yml"
        wf.parent.mkdir(parents=True)
        wf.write_text(text)
        env = {
            "GIT_AUTHOR_NAME": "x",
            "GIT_AUTHOR_EMAIL": "x@x",
            "GIT_COMMITTER_NAME": "x",
            "GIT_COMMITTER_EMAIL": "x@x",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        }
        subprocess.run(["git", "init", "-q", tmp], check=True, env=env)
        subprocess.run(["git", "-C", tmp, "add", "."], check=True, env=env)
        subprocess.run(["git", "-C", tmp, "commit", "-qm", "case"], check=True, env=env)
        out = subprocess.run(
            [POUTINE, "analyze_local", tmp, "-f", "json", "-q", "--disable-version-check"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    data = json.loads(out.stdout or "{}")
    levels = {rid: r.get("level", "") for rid, r in (data.get("rules") or {}).items()}
    return {
        (f["rule_id"], json.dumps(f.get("meta", {}).get("job", ""), sort_keys=True))
        for f in data.get("findings") or []
        if levels.get(f["rule_id"]) in ("error", "warning")
    }


def main(out: str) -> None:
    have_zizmor = zizmor.available()
    have_poutine = Path(POUTINE).exists()
    rows = []
    for case_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        meta = json.loads((case_dir / "case.json").read_text())
        row: dict[str, object] = {"case": case_dir.name, "title": meta["title"]}
        if not meta["workflow_change_visible"]:
            row.update(
                pipedelta="cannot see",
                zizmor="cannot see",
                poutine="cannot see",
                combined="cannot see",
            )
            rows.append(row)
            continue
        b = case_dir / "before.yml"
        before = b.read_text() if b.exists() else None
        after = (case_dir / "after.yml").read_text()

        own = overall(compare(before, after)) == "high"
        row["pipedelta"] = "blocked" if own else "missed"

        z_new = zizmor.new_findings(before, after, "case.yml") if have_zizmor else []
        z_high = sorted({ident for ident, _job, f in z_new if f.level == "high"})
        row["zizmor"] = ("flagged" if z_high else "missed") if have_zizmor else "not run"
        row["zizmor_new_high"] = z_high

        if have_poutine:
            p_new = sorted({r for r, _ in _poutine_findings(after) - _poutine_findings(before)})
            row["poutine"] = "flagged" if p_new else "missed"
            row["poutine_new"] = p_new
        else:
            row["poutine"] = "not run"

        merged = zizmor.merge(compare(before, after), z_new)
        row["combined"] = "blocked" if overall(merged) == "high" else "missed"
        rows.append(row)

    result = {
        "tools": {
            "zizmor": _version(["zizmor", "--version"]) if have_zizmor else "not installed",
            "poutine": _version([POUTINE, "version"]) if have_poutine else "not installed",
        },
        "cases": rows,
    }
    Path(out).write_text(json.dumps(result, indent=2) + "\n")
    print(result["tools"])
    print(f"{'case':34} {'pipedelta':10} {'zizmor':10} {'poutine':10} {'combined':10}")
    for r in rows:
        print(
            f"{r['case']:34} {r['pipedelta']:10} {r['zizmor']:10} {r['poutine']:10} "
            f"{r['combined']:10}"
        )
    for tool, word in (
        ("pipedelta", "blocked"),
        ("zizmor", "flagged"),
        ("poutine", "flagged"),
        ("combined", "blocked"),
    ):
        print(tool, sum(r[tool] == word for r in rows), "of", len(rows))


if __name__ == "__main__":
    main(sys.argv[1])
