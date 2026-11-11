"""Command-line interface.

flakelab run    --runner docker --image my-app:latest --out results
flakelab run    --runner local  --repo path/to/project --out results
flakelab serve  --dir results --port 8080
flakelab report --results results/results.json
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shlex
import shutil
import sys
from pathlib import Path

from flakelab import __version__
from flakelab.conditions import ALL_CONDITIONS, get_conditions
from flakelab.experiment import DASHBOARD_DIR, Experiment
from flakelab.report import render_markdown
from flakelab.runners import DockerRunner, LocalRunner


def _cmd_run(args) -> int:
    pytest_args = shlex.split(args.pytest_args)
    runner: DockerRunner | LocalRunner
    if args.runner == "docker":
        if not args.image:
            print("error: --image is required with --runner docker", file=sys.stderr)
            return 2
        runner = DockerRunner(
            args.image, pytest_args, network=args.docker_network, timeout=args.timeout
        )
        try:
            runner.check()
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        project = args.project or args.image
    else:
        runner = LocalRunner(args.repo, pytest_args, timeout=args.timeout)
        project = args.project or Path(args.repo).resolve().name

    try:
        conditions = get_conditions(args.conditions.split(",") if args.conditions else None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    expected = None
    if args.expected:
        expected = json.loads(Path(args.expected).read_text())

    exp = Experiment(
        runner,
        conditions,
        runs=args.runs,
        out_dir=args.out,
        seed=args.seed,
        workers=args.workers,
        alpha=args.alpha,
        expected=expected,
        project=project,
    )
    doc = exp.run()
    s = doc["summary"]
    print(
        f"\n{s['tests']} tests | {s['baseline_flaky']} flaky at baseline | "
        f"{s['hidden_sensitivities']} hidden sensitivities | "
        f"{s['supported_hypotheses']} supported hypotheses | {s['unknown']} unknown"
    )
    print(f"Open the dashboard: flakelab serve --dir {args.out}")
    if args.fail_on_findings and (s["supported_hypotheses"] or s["unknown"]):
        return 1
    return 0


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # keep the console quiet
        pass


def _cmd_serve(args) -> int:
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    index = directory / "index.html"
    if not index.exists():
        shutil.copy(DASHBOARD_DIR / "index.html", index)
    handler = functools.partial(_Handler, directory=str(directory))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"FlakeLab dashboard: http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_report(args) -> int:
    doc = json.loads(Path(args.results).read_text())
    print(render_markdown(doc))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flakelab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--version", action="version", version=f"FlakeLab {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the experiment")
    r.add_argument("--runner", choices=["docker", "local"], default="docker")
    r.add_argument("--image", help="Docker image containing the project and pytest")
    r.add_argument("--repo", default=".", help="project folder (local runner)")
    r.add_argument("--docker-network", help="Docker network to attach test containers to")
    r.add_argument("--runs", type=int, default=10, help="runs per condition (default 10)")
    r.add_argument(
        "--conditions",
        help="comma-separated, default all: " + ",".join(c.name for c in ALL_CONDITIONS),
    )
    r.add_argument("--pytest-args", default="", help='extra pytest args, e.g. "tests"')
    r.add_argument("--out", default="flakelab-results", help="output folder")
    r.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel runs (default 1; more is faster but parallel runs "
        "compete for CPU and can blur CPU experiments)",
    )
    r.add_argument("--seed", type=int, default=42, help="seed for shuffled order")
    r.add_argument("--alpha", type=float, default=0.05, help="significance level")
    r.add_argument("--timeout", type=int, default=600, help="seconds per run")
    r.add_argument("--expected", help="JSON of known causes, for evaluation")
    r.add_argument("--project", help="project name shown in the report")
    r.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit with code 1 if any unreliable test is found",
    )
    r.set_defaults(func=_cmd_run)

    s = sub.add_parser("serve", help="serve the live dashboard")
    s.add_argument("--dir", default="flakelab-results")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8080)
    s.set_defaults(func=_cmd_serve)

    rep = sub.add_parser("report", help="print the Markdown report")
    rep.add_argument("--results", default="flakelab-results/results.json")
    rep.set_defaults(func=_cmd_report)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
