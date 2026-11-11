"""Reproduction capsules (Pillar C).

"Don't just trust the diagnosis. Reproduce the experiment yourself."

A capsule is a small folder that captures everything needed to re-create one
investigated failure:

    capsule.json        what was tested, under which condition, with what result
    order.txt           the exact test order of a recorded failing run, up to
                        and including the failing test
    plugin/             the FlakeLab pytest plugin that replays that order
    reproduce.sh        one command for Linux / macOS / Git Bash
    reproduce.ps1       one command for Windows PowerShell
    README.md           the same in plain words

`flakelab capsule verify <folder>` re-runs the capsule (condition vs baseline,
interleaved) and checks statistically whether the failure is reproduced.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flakelab import __version__
from flakelab.analyzer import FAIL_OUTCOMES
from flakelab.conditions import BASELINE, BASELINE_ENV, Condition
from flakelab.runners import ORDER_FILE_NAME, PLUGIN_DIR, PLUGIN_NAME, DockerRunner, LocalRunner
from flakelab.stats import fisher_one_sided

CAPSULE_VERSION = 1
CONTAINER_CAPSULE_DIR = "/capsule"


def _slug(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid.replace("::", "__")).strip("_")[:120]


def _pick_failing_run(doc: dict, nodeid: str, condition: str) -> dict | None:
    candidates = [
        r
        for r in doc["runs"]
        if r["condition"] == condition and r["outcomes"].get(nodeid) in FAIL_OUTCOMES
    ]
    return min(candidates, key=lambda r: r["index"]) if candidates else None


def _order_prefix(order: list, nodeid: str) -> list:
    """Tests that ran before the failing test, plus the test itself."""
    if nodeid in order:
        return order[: order.index(nodeid) + 1]
    return [nodeid]


def _condition_env(cond_meta: dict, run: dict) -> dict:
    """Environment of the recorded run, without FlakeLab's own bookkeeping."""
    env = dict(BASELINE_ENV)
    env.update(cond_meta.get("env") or {})
    env.pop("FLAKELAB_ORDER", None)  # replaced by the explicit order file
    return env


def _docker_command(capsule: dict, mount: str) -> list[str]:
    cond = capsule["condition"]
    parts = ["docker", "run", "--rm"]
    network = capsule["environment"].get("network")
    if network and "--network" not in cond["docker_args"]:
        parts += ["--network", network]
    parts += list(cond["docker_args"])
    for key, value in cond["env"].items():
        parts += ["-e", f"{key}={value}"]
    parts += [
        "-e",
        f"FLAKELAB_ORDER=explicit:{CONTAINER_CAPSULE_DIR}/{ORDER_FILE_NAME}",
        "-e",
        f"PYTHONPATH={CONTAINER_CAPSULE_DIR}/plugin",
        "-v",
        f"{mount}:{CONTAINER_CAPSULE_DIR}:ro",
        capsule["image"]["run_reference"],
        "python",
        "-m",
        "pytest",
        "-p",
        PLUGIN_NAME,
        "-p",
        "no:cacheprovider",
        "-v",
    ]
    return parts


def build_capsule(doc: dict, test: dict) -> dict | None:
    """Describe one capsule as a dictionary (no files written)."""
    v = test["verdict"]
    if v["level"] == "supported_hypothesis" and test.get("reproduce"):
        cond_name = test["reproduce"]["condition"]
    elif v["level"] in ("unknown", "weak_signal"):
        cond_name = "baseline"  # no condition explains it: replay a failing baseline run
    else:
        return None
    run = _pick_failing_run(doc, test["nodeid"], cond_name)
    if run is None:
        return None
    conditions = {c["name"]: c for c in doc["meta"]["conditions"]}
    cond_meta = conditions[cond_name]
    env_meta = doc["meta"].get("environment") or {}
    image = env_meta.get("image") or {}
    digests = image.get("repo_digests") or []
    # Prefer the local tag (works offline, on the machine that ran the experiment);
    # the registry digest, when present, is recorded for exact cross-machine pulls.
    run_reference = image.get("reference") or (digests[0] if digests else "")
    per = test["per_condition"]
    order_env = run.get("order_env", "")
    seed = order_env.split(":", 1)[1] if order_env.startswith("random:") else None
    return {
        "capsule_version": CAPSULE_VERSION,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flakelab_version": __version__,
        "test": test["nodeid"],
        "diagnosis": {
            "level": v["level"],
            "title": v["title"],
            "categories": v["categories"],
            "explanation": v["explanation"],
            "observations": [o["text"] for o in test["observations"] if o["significant"]],
        },
        "condition": {
            "name": cond_name,
            "label": cond_meta["label"],
            "category": cond_meta["category"],
            "description": cond_meta["description"],
            "docker_args": list(cond_meta.get("docker_args") or []),
            "env": _condition_env(cond_meta, run),
            "cpu_limit": _flag(cond_meta, "--cpus"),
            "memory_limit": _flag(cond_meta, "--memory"),
            "network": _flag(cond_meta, "--network") or env_meta.get("network") or "default",
        },
        "execution": {
            "order_mode": "explicit (replays a recorded failing run)",
            "tests": _order_prefix(run.get("order") or [], test["nodeid"]),
            "recorded_order_setting": order_env or "default",
            "shuffle_seed": seed,
            "source_run": {"condition": run["condition"], "index": run["index"]},
        },
        "image": {
            "reference": image.get("reference"),
            "id": image.get("id"),
            "repo_digests": digests,
            "run_reference": run_reference,
            "portable": bool(digests),
            "note": (
                "Pinned by registry digest: anyone can pull exactly this image."
                if digests
                else "Local image (no registry digest). Push it to a registry, or rebuild "
                "it from the recorded repository revision, to reproduce on another machine."
            ),
        },
        "environment": {
            "runner": env_meta.get("runner") or doc["meta"].get("runner"),
            "repository_revision": env_meta.get("repository_revision"),
            "revision_source": env_meta.get("revision_source"),
            "project": env_meta.get("project"),
            "host": env_meta.get("host"),
            "network": env_meta.get("network"),
        },
        "experiment": {
            "runs_per_condition": doc["meta"]["runs_per_condition"],
            "condition_failures": per[cond_name]["failures"],
            "condition_runs": per[cond_name]["runs"],
            "baseline_failures": per["baseline"]["failures"],
            "baseline_runs": per["baseline"]["runs"],
            "all_conditions": {k: [c["failures"], c["runs"]] for k, c in per.items()},
            "alpha": doc["meta"]["alpha"],
        },
        "verification": None,
    }


def _flag(cond_meta: dict, flag: str) -> str | None:
    args = list(cond_meta.get("docker_args") or [])
    return args[args.index(flag) + 1] if flag in args else None


def write_capsule(capsule: dict, out_dir: Path) -> Path:
    folder = out_dir / _slug(capsule["test"])
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "plugin").mkdir(parents=True)
    shutil.copy(PLUGIN_DIR / f"{PLUGIN_NAME}.py", folder / "plugin" / f"{PLUGIN_NAME}.py")
    (folder / ORDER_FILE_NAME).write_text("\n".join(capsule["execution"]["tests"]) + "\n")
    (folder / "capsule.json").write_text(json.dumps(capsule, indent=2) + "\n")

    if capsule["environment"]["runner"] == "docker":
        sh_cmd = " ".join(shlex.quote(p) for p in _docker_command(capsule, "$DIR"))
        sh_cmd = sh_cmd.replace("'$DIR:/capsule:ro'", '"$DIR:/capsule:ro"')
        ps_parts = _docker_command(capsule, "${DIR}")
        ps_cmd = " ".join(f'"{p}"' if " " in p or "$" in p else p for p in ps_parts)
    else:
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in capsule["condition"]["env"].items())
        sh_cmd = (
            f'{env} FLAKELAB_ORDER="explicit:$DIR/{ORDER_FILE_NAME}" '
            f'PYTHONPATH="$DIR/plugin" python -m pytest -p {PLUGIN_NAME} -p no:cacheprovider -v'
        )
        ps_cmd = "# Local capsule: run reproduce.sh from the project folder (Git Bash/WSL)."
    (folder / "reproduce.sh").write_text(
        "#!/usr/bin/env bash\n# Re-runs the recorded failing run once. "
        "Use `flakelab capsule verify` for a statistical check.\n"
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n' + sh_cmd + "\n"
    )
    (folder / "reproduce.sh").chmod(0o755)
    (folder / "reproduce.ps1").write_text(
        "# Re-runs the recorded failing run once (Windows PowerShell).\n"
        "$DIR = $PSScriptRoot\n" + ps_cmd + "\n"
    )
    (folder / "README.md").write_text(_readme(capsule))
    return folder


def _readme(c: dict) -> str:
    cond, ex, img = c["condition"], c["experiment"], c["image"]
    obs = "\n".join(f"- {o}" for o in c["diagnosis"]["observations"]) or "- (none significant)"
    net = c["environment"].get("network")
    deps = (
        f"\nThe project's containers were attached to the Docker network `{net}`. Start the "
        f"services the tests need on that network first (for the demo: "
        f"`docker compose up -d weather-api`).\n"
        if net and cond["name"] != "no_network"
        else ""
    )
    return f"""# Reproduction capsule: `{c["test"]}`

**Diagnosis:** {c["diagnosis"]["title"]} ({c["diagnosis"]["level"].replace("_", " ")})

**Condition:** {cond["label"]}: {cond["description"]}

**What FlakeLab measured**
{obs}

Failed {ex["condition_failures"]}/{ex["condition_runs"]} runs under this condition and \
{ex["baseline_failures"]}/{ex["baseline_runs"]} at baseline.

## Reproduce it

Linux, macOS or Git Bash: `bash reproduce.sh`
Windows PowerShell: `./reproduce.ps1`

This replays the exact test order of a recorded failing run ({len(c["execution"]["tests"])} \
tests, ending with the failing one) under the same condition.
{deps}
A single run may pass: flaky failures are probabilistic. For a proper check:

```
flakelab capsule verify .
```

runs the capsule repeatedly under the condition and at baseline, interleaved, and reports
whether the failure is reproduced with statistical evidence.

## Environment

- Image: `{img["run_reference"]}`. {img["note"]}
- Repository revision: `{c["environment"].get("repository_revision")}`
  ({c["environment"].get("revision_source")})
- Python {((c["environment"].get("project") or {}).get("python"))} on \
{((c["environment"].get("project") or {}).get("os"))}
- Full details (packages, host, Docker flags, environment variables): `capsule.json`

_An association found by controlled experiments, not proof of the root cause._
"""


def create_capsules(doc: dict, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for test in doc["tests"]:
        capsule = build_capsule(doc, test)
        if capsule:
            written.append(write_capsule(capsule, out))
    return written


def verify_capsule(folder: str | Path, runs: int = 10, log=print, runner=None) -> dict:
    """Re-run a capsule under its condition and at baseline, interleaved."""
    folder = Path(folder)
    capsule = json.loads((folder / "capsule.json").read_text())
    cond_meta = capsule["condition"]
    order_file = str(folder / ORDER_FILE_NAME)
    target = capsule["test"]

    condition = Condition(
        name=cond_meta["name"],
        label=cond_meta["label"],
        category=cond_meta["category"],
        description=cond_meta["description"],
        docker_args=tuple(cond_meta["docker_args"]),
        env={k: v for k, v in cond_meta["env"].items() if BASELINE_ENV.get(k) != v},
        needs_docker=bool(cond_meta["docker_args"]),
    )
    # Arms of the verification experiment. Normally both arms replay the recorded
    # order and only the condition differs. For order-dependent failures the order
    # IS the condition, so the baseline arm runs the default order instead.
    is_order = cond_meta["category"] == "order"

    def make_runner(with_order: bool):
        if runner is not None:
            return runner
        order = order_file if with_order else None
        if capsule["environment"]["runner"] == "docker":
            return DockerRunner(
                capsule["image"]["run_reference"],
                [],
                network=capsule["environment"].get("network"),
                order_file=order,
            )
        return LocalRunner(".", [], order_file=order)

    cond_runner = make_runner(True)
    base_runner = make_runner(not is_order)
    if condition.name == "baseline":
        schedule = [("baseline", base_runner, BASELINE, i) for i in range(runs)]
    else:
        schedule = [
            item
            for i in range(runs)
            for item in (
                ("condition", cond_runner, condition, i),
                ("baseline", base_runner, BASELINE, i),
            )
        ]
    counts: dict = {"condition": [0, 0], "baseline": [0, 0]}
    for key, arm_runner, cond, i in schedule:
        res = arm_runner.run(cond, i, 0)
        label = "Recorded order" if (is_order and key == "condition") else cond.label
        outcome = res.outcomes.get(target)
        if outcome is None:
            log(f"  run {i + 1} ({label}): test did not run [{res.note}]")
            continue
        counts[key][1] += 1
        counts[key][0] += outcome in FAIL_OUTCOMES
        log(f"  run {i + 1:>2} {label:<18} {outcome}")

    cf, cr = counts["condition"]
    bf, br = counts["baseline"]
    if condition.name == "baseline":
        p = None
        verdict = "reproduced" if bf else "not_reproduced"
        summary = f"Failed {bf}/{br} replays of the recorded failing run."
    else:
        p = fisher_one_sided(cf, cr, bf, br)
        if cf and p < 0.05:
            verdict = "reproduced"
        elif cf:
            verdict = "partially_reproduced"
        else:
            verdict = "not_reproduced"
        arm = "the recorded test order" if is_order else condition.label
        base = "the default order" if is_order else "baseline"
        summary = (
            f"Failed {cf}/{cr} runs with {arm} vs {bf}/{br} with {base} "
            f"(one-sided Fisher p = {p:.4f})."
        )
    original = capsule["experiment"]
    result = {
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs_per_arm": runs,
        "condition_failures": cf,
        "condition_runs": cr,
        "baseline_failures": bf,
        "baseline_runs": br,
        "p_value": p,
        "verdict": verdict,
        "summary": summary,
        "original": f"{original['condition_failures']}/{original['condition_runs']} vs "
        f"{original['baseline_failures']}/{original['baseline_runs']}",
    }
    (folder / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
