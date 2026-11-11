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
        out_dir: str,
        seed: int = 42,
        workers: int = 1,
        alpha: float = 0.05,
        expected: dict | None = None,
        project: str = "",
        log=print,
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
        self._write("running", total)
        start = time.time()

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

        doc = self._write("done", total)
        self.log(f"Done in {time.time() - start:.0f}s. Results: {self.out / 'results.json'}")
        return doc
