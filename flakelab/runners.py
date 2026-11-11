"""Runners execute the test suite once under one condition.

* DockerRunner: the real thing. Starts a fresh container from the project's
  image for every run, applying CPU / memory / network limits with Docker flags.
  A fresh container per run means no state leaks between runs.
* LocalRunner: runs pytest directly on this machine. It can only apply
  conditions that need no Docker (test order, timezone). Useful for development
  and for machines without Docker.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from flakelab.conditions import Condition

PLUGIN_DIR = Path(__file__).parent / "plugin"
PLUGIN_NAME = "flakelab_pytest_plugin"
CONTAINER_PLUGIN_DIR = "/tmp/flakelab_plugin"
CONTAINER_OUT = "/tmp/flakelab_out.json"


@dataclass
class RunResult:
    condition: str
    index: int
    outcomes: dict = field(default_factory=dict)  # nodeid -> passed/failed/error/crashed
    duration: float = 0.0
    crashed: bool = False
    oom_killed: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "index": self.index,
            "duration": round(self.duration, 2),
            "crashed": self.crashed,
            "oom_killed": self.oom_killed,
            "note": self.note,
            "outcomes": self.outcomes,
        }


def _parse_plugin_output(raw: dict) -> tuple[dict, bool, str]:
    """Turn the plugin's JSON into outcomes. Detects a run that died mid-way."""
    outcomes = {k: v for k, v in raw.get("outcomes", {}).items() if v != "skipped"}
    crashed = not raw.get("finished", False)
    note = ""
    if crashed and raw.get("running"):
        # The test that was running when the process died gets the blame.
        outcomes[raw["running"]] = "crashed"
        note = f"process died while running {raw['running']}"
    return outcomes, crashed, note


class LocalRunner:
    name = "local"

    def __init__(self, repo: str, pytest_args: list[str], timeout: int = 600):
        self.repo = Path(repo).resolve()
        self.pytest_args = pytest_args
        self.timeout = timeout

    def supports(self, condition: Condition) -> bool:
        return not condition.needs_docker

    def describe(self) -> str:
        return f"local pytest in {self.repo}"

    def reproduce_command(self, condition: Condition, nodeid: str) -> str:
        env_part = " ".join(
            f"{k}={shlex.quote(v)}" for k, v in condition.env.items() if k != "FLAKELAB_ORDER"
        )
        return f"{env_part} python -m pytest {shlex.quote(nodeid)}".strip()

    def run(self, condition: Condition, index: int, seed: int) -> RunResult:
        start = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            out_file = os.path.join(tmp, "out.json")
            env = dict(os.environ)
            env.update(condition.full_env(index, seed))
            env["FLAKELAB_OUT"] = out_file
            env["PYTHONPATH"] = os.pathsep.join(
                [str(PLUGIN_DIR), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep)
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                PLUGIN_NAME,
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                "no:randomly",
                *self.pytest_args,
            ]
            note = ""
            try:
                subprocess.run(
                    cmd,
                    cwd=self.repo,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                note = f"run timed out after {self.timeout}s"
            result = RunResult(condition.name, index, duration=time.time() - start)
            if os.path.exists(out_file):
                with open(out_file) as fh:
                    outcomes, crashed, crash_note = _parse_plugin_output(json.load(fh))
                result.outcomes, result.crashed = outcomes, crashed
                result.note = note or crash_note
            else:
                result.crashed, result.note = True, note or "pytest produced no results"
            return result


class DockerRunner:
    name = "docker"

    def __init__(
        self,
        image: str,
        pytest_args: list[str],
        network: str | None = None,
        timeout: int = 600,
        docker_bin: str = "docker",
    ):
        self.image = image
        self.pytest_args = pytest_args
        self.network = network
        self.timeout = timeout
        self.docker = docker_bin

    def supports(self, condition: Condition) -> bool:
        return True

    def describe(self) -> str:
        net = f" on network {self.network}" if self.network else ""
        return f"Docker image {self.image}{net}"

    def check(self) -> None:
        """Fail early with a clear message if Docker or the image is missing."""
        try:
            subprocess.run([self.docker, "version"], capture_output=True, check=True, timeout=30)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Docker is not available. Start Docker Desktop and retry.") from exc
        found = subprocess.run(
            [self.docker, "image", "inspect", self.image], capture_output=True, check=False
        )
        if found.returncode != 0:
            raise RuntimeError(
                f"Docker image '{self.image}' not found. Build it first (see README)."
            )

    def _create_args(self, condition: Condition, index: int, seed: int, name: str) -> list[str]:
        args = [self.docker, "create", "--name", name]
        docker_args = list(condition.docker_args)
        # Attach to the project network unless this condition cuts the network.
        if self.network and "--network" not in docker_args:
            args += ["--network", self.network]
        args += docker_args
        env = condition.full_env(index, seed)
        env["FLAKELAB_OUT"] = CONTAINER_OUT
        env["PYTHONPATH"] = CONTAINER_PLUGIN_DIR
        for key, value in env.items():
            args += ["-e", f"{key}={value}"]
        args += [
            self.image,
            "python",
            "-m",
            "pytest",
            "-p",
            PLUGIN_NAME,
            "-q",
            "-p",
            "no:cacheprovider",
            *self.pytest_args,
        ]
        return args

    def reproduce_command(self, condition: Condition, nodeid: str) -> str:
        parts = ["docker", "run", "--rm"]
        docker_args = list(condition.docker_args)
        if self.network and "--network" not in docker_args:
            parts += ["--network", self.network]
        parts += docker_args
        for key, value in condition.env.items():
            if key == "FLAKELAB_ORDER":
                continue  # the command runs the test alone (see analyzer)
            parts += ["-e", f"{key}={value}"]
        parts += [self.image, "python", "-m", "pytest", nodeid]
        return " ".join(shlex.quote(p) for p in parts)

    def run(self, condition: Condition, index: int, seed: int) -> RunResult:
        name = f"flakelab-{uuid.uuid4().hex[:12]}"
        start = time.time()
        result = RunResult(condition.name, index)
        try:
            subprocess.run(
                self._create_args(condition, index, seed, name),
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            # Copy the plugin into the container before it starts. No image
            # rebuild is needed, so FlakeLab works with any project image.
            subprocess.run(
                [self.docker, "cp", str(PLUGIN_DIR), f"{name}:{CONTAINER_PLUGIN_DIR}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            try:
                subprocess.run(
                    [self.docker, "start", "-a", name],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                subprocess.run([self.docker, "kill", name], capture_output=True, check=False)
                result.note = f"run timed out after {self.timeout}s"
            state = subprocess.run(
                [self.docker, "inspect", "--format", "{{.State.OOMKilled}}", name],
                capture_output=True,
                text=True,
                check=False,
            )
            result.oom_killed = state.stdout.strip() == "true"
            with tempfile.TemporaryDirectory() as tmp:
                local_out = os.path.join(tmp, "out.json")
                copied = subprocess.run(
                    [self.docker, "cp", f"{name}:{CONTAINER_OUT}", local_out],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if copied.returncode == 0 and os.path.exists(local_out):
                    with open(local_out) as fh:
                        outcomes, crashed, note = _parse_plugin_output(json.load(fh))
                    result.outcomes, result.crashed = outcomes, crashed
                    result.note = result.note or note
                else:
                    result.crashed = True
                    result.note = result.note or "container produced no results"
        except subprocess.CalledProcessError as exc:
            result.crashed = True
            result.note = f"docker error: {(exc.stderr or '').strip()[:300]}"
        finally:
            subprocess.run([self.docker, "rm", "-f", name], capture_output=True, check=False)
            result.duration = time.time() - start
        if result.oom_killed and not result.note:
            result.note = "container was killed by the out-of-memory killer"
        return result
