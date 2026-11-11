"""Runs the whole experiment and keeps results.json up to date while it runs,
so the dashboard can show results filling in live."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flakelab import __version__
from flakelab.analyzer import analyze
from flakelab.conditions import Condition
from flakelab.report import render_markdown

DASHBOARD_DIR = Path(__file__).parent / "dashboard"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_schedule(conditions: list[Condition], runs: int, runner) -> list[tuple]:
    """Interleave conditions (baseline, cpu, memory, ..., baseline, cpu, ...).

    Running all baseline runs first and all CPU runs last would let anything
    that changes over time (laptop heating up, other programs starting) look
    like an effect of the condition. Interleaving spreads that noise evenly.
    """
    schedule = []
    for i in range(runs):
        for cond in conditions:
            if runner.supports(cond):
                schedule.append((cond, i))
    return schedule


class Experiment:
    def __init__(
        self,
        runner,
        conditions: list[Condition],
        runs: int,
        out_dir: str | Path,
        seed: int = 42,
        workers: int = 1,
        alpha: float = 0.05,
        expected: dict | None = None,
        project: str = "",
        log=print,
        capsules: bool = True,
    ):
        self.runner = runner
        self.conditions = conditions
        self.active = [c for c in conditions if runner.supports(c)]
        self.skipped = [c for c in conditions if not runner.supports(c)]
        self.runs = runs
        self.out = Path(out_dir)
        self.seed = seed
        self.workers = max(1, workers)
        self.alpha = alpha
        self.expected = expected
        self.project = project
        self.log = log
        self.results: list[dict] = []
        self.lock = threading.Lock()
        self.started = _now()
        self.make_capsules = capsules
        self.environment: dict = {}
        self.timing: dict = {}
        self.capsules: list[dict] = []

    def _meta(self, status: str, total: int) -> dict:
        return {
            "tool": "FlakeLab",
            "version": __version__,
            "project": self.project,
            "runner": self.runner.name,
            "target": self.runner.describe(),
            "status": status,
            "started_at": self.started,
            "updated_at": _now(),
            "runs_per_condition": self.runs,
            "total_runs": total,
            "completed_runs": len(self.results),
            "workers": self.workers,
            "seed": self.seed,
            "alpha": self.alpha,
            "conditions": [
                {
                    "name": c.name,
                    "label": c.label,
                    "category": c.category,
                    "description": c.description,
                    "docker_args": list(c.docker_args),
                    "env": dict(c.env),
                }
                for c in self.active
            ],
            "skipped_conditions": [
                {
                    "name": c.name,
                    "label": c.label,
                    "reason": f"needs Docker (runner is {self.runner.name})",
                }
                for c in self.skipped
            ],
            "environment": self.environment,
            "timing": self.timing,
            "capsules": self.capsules,
        }

    def _write(self, status: str, total: int) -> dict:
        analysis = analyze(
            self.results, self.active, runner=self.runner, alpha=self.alpha, expected=self.expected
        )
        doc = {"meta": self._meta(status, total), **analysis, "runs": self.results}
        tmp = self.out / "results.json.tmp"
        with open(tmp, "w") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, self.out / "results.json")
        (self.out / "report.md").write_text(render_markdown(doc))
        return doc

    def run(self) -> dict:
        self.out.mkdir(parents=True, exist_ok=True)
        for name in ("index.html",):
            shutil.copy(DASHBOARD_DIR / name, self.out / name)
        schedule = build_schedule(self.conditions, self.runs, self.runner)
        total = len(schedule)
        if self.skipped:
            self.log("Skipping (need Docker): " + ", ".join(c.label for c in self.skipped))
        self.log(
            f"FlakeLab {__version__}: {total} runs "
            f"({len(self.active)} conditions x {self.runs}) on {self.runner.describe()}"
        )
        if hasattr(self.runner, "environment"):
            self.log("Recording the environment (image, Python, packages, host)...")
            try:
                self.environment = self.runner.environment()
            except Exception as exc:  # never let bookkeeping stop an experiment
                self.environment = {"error": f"could not record environment: {exc}"}
        self._write("running", total)
        start = time.time()
        cpu_start = _process_cpu_seconds()

        def one(item):
            cond, i = item
            res = self.runner.run(cond, i, self.seed).to_dict()
            with self.lock:
                self.results.append(res)
                done = len(self.results)
                failed = sum(1 for o in res["outcomes"].values() if o != "passed")
                extra = f" [{res['note']}]" if res["note"] else ""
                self.log(
                    f"[{done:>3}/{total}] {cond.label:<18} run {i + 1:<3} "
                    f"{failed} failing  {res['duration']:.1f}s{extra}"
                )
                self._write("running", total)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(one, schedule))

        self.timing = _timing(self.results, time.time() - start, cpu_start)
        doc = self._write("done", total)
        if self.make_capsules:
            from flakelab.capsule import create_capsules  # avoid an import cycle

            folders = create_capsules(doc, self.out / "capsules")
            self.capsules = [
                {
                    "test": json.loads((f / "capsule.json").read_text())["test"],
                    "path": f"capsules/{f.name}",
                }
                for f in folders
            ]
            doc = self._write("done", total)
            self.log(f"Wrote {len(folders)} reproduction capsules to {self.out / 'capsules'}")
        self.log(f"Done in {time.time() - start:.0f}s. Results: {self.out / 'results.json'}")
        return doc


def _process_cpu_seconds() -> float | None:
    """CPU time used by FlakeLab's own process (not the tests). Unix only."""
    try:
        import resource
    except ImportError:  # Windows
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _max_rss_mb() -> float | None:
    try:
        import resource
        import sys
    except ImportError:
        return None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes, macOS bytes.
    return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def _timing(results: list[dict], wall: float, cpu_start: float | None) -> dict:
    """Measured cost of the experiment, so overhead is reported, not guessed."""
    durations = [r["duration"] for r in results]
    inside = [r["pytest_seconds"] for r in results if r.get("pytest_seconds") is not None]
    overheads = [
        r["duration"] - r["pytest_seconds"] for r in results if r.get("pytest_seconds") is not None
    ]
    cpu_end = _process_cpu_seconds()
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {
        "wall_seconds": round(wall, 2),
        "runs": len(results),
        "mean_run_seconds": mean(durations),
        "mean_pytest_seconds": mean(inside),
        "mean_overhead_seconds": mean(overheads),
        "overhead_note": "overhead = run wall time minus time inside pytest "
        "(container create/start/copy/remove for Docker; interpreter start for local)",
        "flakelab_cpu_seconds": round(cpu_end - cpu_start, 2)
        if cpu_end is not None and cpu_start is not None
        else None,
        "flakelab_max_rss_mb": _max_rss_mb(),
    }
