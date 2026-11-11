"""Runners execute the test suite once under one condition.

* DockerRunner: the real thing. Starts a fresh container from the project's
  image for every run, applying CPU / memory / network limits with Docker flags.
  A fresh container per run means no state leaks between runs.
* LocalRunner: runs pytest directly on this machine. It can only apply
  conditions that need no Docker (test order, timezone). Useful for development
  and for machines without Docker.

Both can replay an exact test order from a file (`order_file`), which is how
reproduction capsules re-create a recorded failing run.
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
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
ORDER_FILE_NAME = "order.txt"

# Runs inside the project's environment to record what it contains. Standard
# library only, because FlakeLab is not installed there.
ENV_PROBE = r"""
import importlib.metadata as md, json, locale, os, platform, sys, time
try:
    release = dict(l.strip().split("=", 1) for l in open("/etc/os-release") if "=" in l)
    os_name = release.get("PRETTY_NAME", "").strip('"')
except OSError:
    os_name = platform.platform()
print(json.dumps({
    "python": sys.version.split()[0],
    "python_implementation": platform.python_implementation(),
    "os": os_name,
    "architecture": platform.machine(),
    "packages": sorted(f"{d.metadata['Name']}=={d.version}" for d in md.distributions()),
    "timezone": time.tzname[0],
    "TZ": os.environ.get("TZ"),
    "locale": locale.setlocale(locale.LC_ALL, None),
    "preferred_encoding": locale.getpreferredencoding(False),
}))
"""


@dataclass
class RunResult:
    condition: str
    index: int
    outcomes: dict = field(default_factory=dict)  # nodeid -> passed/failed/error/crashed
    order: list = field(default_factory=list)  # nodeids in the order they were collected
    order_env: str = ""  # the FLAKELAB_ORDER value used (holds the shuffle seed)
    duration: float = 0.0  # wall-clock seconds for the whole run, including Docker
    pytest_seconds: float | None = None  # time spent inside pytest itself
    crashed: bool = False
    oom_killed: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "index": self.index,
            "duration": round(self.duration, 3),
            "pytest_seconds": self.pytest_seconds,
            "crashed": self.crashed,
            "oom_killed": self.oom_killed,
            "note": self.note,
            "order_env": self.order_env,
            "order": self.order,
            "outcomes": self.outcomes,
        }


def _apply_plugin_output(result: RunResult, raw: dict) -> None:
    """Copy the plugin's JSON into a RunResult. Detects a run that died mid-way."""
    result.outcomes = {k: v for k, v in raw.get("outcomes", {}).items() if v != "skipped"}
    result.order = raw.get("collected", [])
    result.order_env = raw.get("order", "")
    result.pytest_seconds = raw.get("elapsed")
    result.crashed = not raw.get("finished", False)
    if result.crashed and raw.get("running"):
        # The test that was running when the process died gets the blame.
        result.outcomes[raw["running"]] = "crashed"
        result.note = result.note or f"process died while running {raw['running']}"


def _parse_plugin_output(raw: dict) -> tuple[dict, bool, str]:
    """Kept for callers that only need outcomes."""
    tmp = RunResult("", 0)
    _apply_plugin_output(tmp, raw)
    return tmp.outcomes, tmp.crashed, tmp.note


def _git_revision(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.strip() or None


class LocalRunner:
    name = "local"

    def __init__(
        self,
        repo: str,
        pytest_args: list[str],
        timeout: int = 600,
        order_file: str | None = None,
    ):
        self.repo = Path(repo).resolve()
        self.pytest_args = pytest_args
        self.timeout = timeout
        self.order_file = str(Path(order_file).resolve()) if order_file else None

    def supports(self, condition: Condition) -> bool:
        return not condition.needs_docker

    def describe(self) -> str:
        return f"local pytest in {self.repo}"

    def reproduce_command(self, condition: Condition, nodeid: str) -> str:
        env_part = " ".join(
            f"{k}={shlex.quote(v)}" for k, v in condition.env.items() if k != "FLAKELAB_ORDER"
        )
        return f"{env_part} python -m pytest {shlex.quote(nodeid)}".strip()

    def environment(self) -> dict:
        probe = subprocess.run(
            [sys.executable, "-c", ENV_PROBE],
            capture_output=True,
            text=True,
            cwd=self.repo,
            timeout=60,
            check=False,
        )
        project = json.loads(probe.stdout) if probe.returncode == 0 else {}
        return {
            "runner": "local",
            "project": project,
            "host": {"platform": platform.platform(), "cpus": os.cpu_count()},
            "repository_revision": _git_revision(self.repo),
            "revision_source": "git rev-parse HEAD in the project folder",
        }

    def run(self, condition: Condition, index: int, seed: int) -> RunResult:
        start = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            out_file = os.path.join(tmp, "out.json")
            env = dict(os.environ)
            env.update(condition.full_env(index, seed))
            if self.order_file:
                env["FLAKELAB_ORDER"] = f"explicit:{self.order_file}"
            env["FLAKELAB_OUT"] = out_file
            env["PYTHONPATH"] = os.pathsep.join(
                [str(PLUGIN_DIR), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep)
            cmd = [sys.executable, "-m", "pytest", "-p", PLUGIN_NAME, "-q"]
            cmd += ["-p", "no:cacheprovider", "-p", "no:randomly", *self.pytest_args]
            result = RunResult(condition.name, index)
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
                result.note = f"run timed out after {self.timeout}s"
            result.duration = time.time() - start
            if os.path.exists(out_file):
                with open(out_file) as fh:
                    _apply_plugin_output(result, json.load(fh))
            else:
                result.crashed = True
                result.note = result.note or "pytest produced no results"
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
        order_file: str | None = None,
    ):
        self.image = image
        self.pytest_args = pytest_args
        self.network = network
        self.timeout = timeout
        self.docker = docker_bin
        self.order_file = order_file

    def supports(self, condition: Condition) -> bool:
        return True

    def describe(self) -> str:
        net = f" on network {self.network}" if self.network else ""
        return f"Docker image {self.image}{net}"

    def _docker(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.docker, *args], capture_output=True, text=True, timeout=timeout, check=False
        )

    def check(self) -> None:
        """Fail early with a clear message if Docker or the image is missing."""
        try:
            subprocess.run([self.docker, "version"], capture_output=True, check=True, timeout=30)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Docker is not available. Start Docker Desktop and retry.") from exc
        if self._docker("image", "inspect", self.image).returncode != 0:
            raise RuntimeError(
                f"Docker image '{self.image}' not found. Build or pull it first (see README)."
            )

    def environment(self) -> dict:
        """Record exactly what was tested: image identity, contents and host."""
        image: dict = {"reference": self.image}
        inspected = self._docker("image", "inspect", self.image)
        if inspected.returncode == 0:
            data = json.loads(inspected.stdout)[0]
            labels = (data.get("Config") or {}).get("Labels") or {}
            image.update(
                id=data.get("Id"),
                repo_digests=data.get("RepoDigests") or [],
                created=data.get("Created"),
                os=data.get("Os"),
                architecture=data.get("Architecture"),
                labels=labels,
            )
        probe = self._docker(
            "run", "--rm", "--network", "none", self.image, "python", "-c", ENV_PROBE, timeout=180
        )
        project = json.loads(probe.stdout) if probe.returncode == 0 else {}
        host_info = self._docker(
            "info",
            "--format",
            "{{json .ServerVersion}}|{{json .NCPU}}|{{json .MemTotal}}|"
            "{{json .OperatingSystem}}|{{json .CgroupVersion}}",
        )
        host: dict = {}
        if host_info.returncode == 0:
            try:
                keys = ["docker_version", "cpus", "memory_bytes", "os", "cgroup_version"]
                values = [json.loads(v) for v in host_info.stdout.strip().split("|")]
                host = dict(zip(keys, values, strict=True))
            except ValueError:
                host = {"raw": host_info.stdout.strip()}
        revision = (image.get("labels") or {}).get("org.opencontainers.image.revision")
        source = "image label org.opencontainers.image.revision"
        if not revision:
            revision = os.environ.get("GITHUB_SHA") or _git_revision(Path.cwd())
            source = "GITHUB_SHA or git rev-parse in the working directory (best effort)"
        return {
            "runner": "docker",
            "image": image,
            "project": project,
            "host": host,
            "network": self.network,
            "repository_revision": revision,
            "revision_source": source,
        }

    def _env(self, condition: Condition, index: int, seed: int) -> dict:
        env = condition.full_env(index, seed)
        if self.order_file:
            env["FLAKELAB_ORDER"] = f"explicit:{CONTAINER_PLUGIN_DIR}/{ORDER_FILE_NAME}"
        env["FLAKELAB_OUT"] = CONTAINER_OUT
        env["PYTHONPATH"] = CONTAINER_PLUGIN_DIR
        return env

    def _create_args(self, condition: Condition, index: int, seed: int, name: str) -> list[str]:
        args = [self.docker, "create", "--name", name]
        docker_args = list(condition.docker_args)
        # Attach to the project network unless this condition cuts the network.
        if self.network and "--network" not in docker_args:
            args += ["--network", self.network]
        args += docker_args
        for key, value in self._env(condition, index, seed).items():
            args += ["-e", f"{key}={value}"]
        args += [self.image, "python", "-m", "pytest", "-p", PLUGIN_NAME, "-q"]
        args += ["-p", "no:cacheprovider", *self.pytest_args]
        return args

    def reproduce_command(self, condition: Condition, nodeid: str) -> str:
        parts = ["docker", "run", "--rm"]
        docker_args = list(condition.docker_args)
        if self.network and "--network" not in docker_args:
            parts += ["--network", self.network]
        parts += docker_args
        for key, value in condition.env.items():
            if key == "FLAKELAB_ORDER":
                continue  # the quick command runs the test alone; capsules replay order
            parts += ["-e", f"{key}={value}"]
        parts += [self.image, "python", "-m", "pytest", nodeid]
        return " ".join(shlex.quote(p) for p in parts)

    def _plugin_source(self, tmp: str) -> str:
        """The folder copied into the container: the plugin, plus the order file."""
        if not self.order_file:
            return str(PLUGIN_DIR)
        target = os.path.join(tmp, "plugin")
        shutil.copytree(PLUGIN_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(self.order_file, os.path.join(target, ORDER_FILE_NAME))
        return target

    def run(self, condition: Condition, index: int, seed: int) -> RunResult:
        name = f"flakelab-{uuid.uuid4().hex[:12]}"
        start = time.time()
        result = RunResult(condition.name, index)
        try:
            with tempfile.TemporaryDirectory() as tmp:
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
                    [self.docker, "cp", self._plugin_source(tmp), f"{name}:{CONTAINER_PLUGIN_DIR}"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=120,
                )
                try:
                    self._docker("start", "-a", name, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    self._docker("kill", name)
                    result.note = f"run timed out after {self.timeout}s"
                state = self._docker("inspect", "--format", "{{.State.OOMKilled}}", name)
                result.oom_killed = state.stdout.strip() == "true"
                local_out = os.path.join(tmp, "out.json")
                copied = self._docker("cp", f"{name}:{CONTAINER_OUT}", local_out)
                if copied.returncode == 0 and os.path.exists(local_out):
                    with open(local_out) as fh:
                        _apply_plugin_output(result, json.load(fh))
                else:
                    result.crashed = True
                    result.note = result.note or "container produced no results"
        except subprocess.CalledProcessError as exc:
            result.crashed = True
            result.note = f"docker error: {(exc.stderr or '').strip()[:300]}"
        finally:
            self._docker("rm", "-f", name)
            result.duration = time.time() - start
        if result.oom_killed and not result.note:
            result.note = "out-of-memory kill inside the container"
        return result
