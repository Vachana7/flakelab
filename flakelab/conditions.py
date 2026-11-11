"""Experimental conditions.

Each condition changes exactly ONE thing about the environment compared to the
baseline. That is what makes it a controlled experiment: if a test fails much
more often under a condition, the one thing we changed is associated with the
failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The baseline pins the variables we later change, so every condition differs
# from it in exactly one way. "UTC0" is a POSIX timezone string, which works
# even in slim Docker images that have no timezone database installed.
BASELINE_ENV = {"TZ": "UTC0", "FLAKELAB_ORDER": "default"}


@dataclass(frozen=True)
class Condition:
    name: str  # machine name, e.g. "cpu_low"
    label: str  # short label for the dashboard
    category: str  # cpu | memory | network | order | timezone | baseline
    description: str  # what is changed, in plain words
    docker_args: tuple = ()  # extra `docker create` flags
    env: dict = field(default_factory=dict)  # env vars layered on top of BASELINE_ENV
    needs_docker: bool = False  # True if only the Docker runner can apply it

    def full_env(self, run_index: int, seed: int) -> dict:
        env = dict(BASELINE_ENV)
        env.update(self.env)
        if env.get("FLAKELAB_ORDER") == "random":
            # A different (but reproducible) shuffle for every run.
            env["FLAKELAB_ORDER"] = f"random:{seed * 1000 + run_index}"
        return env


BASELINE = Condition(
    name="baseline",
    label="Baseline",
    category="baseline",
    description="Normal resources, network on, default test order, UTC timezone.",
)

ALL_CONDITIONS: list[Condition] = [
    BASELINE,
    Condition(
        name="cpu_low",
        label="CPU 0.25 core",
        category="cpu",
        description="Container limited to a quarter of one CPU core (--cpus 0.25).",
        docker_args=("--cpus", "0.25"),
        needs_docker=True,
    ),
    Condition(
        name="memory_low",
        label="Memory 128 MB",
        category="memory",
        description="Container limited to 128 MB of RAM with no swap (--memory 128m).",
        docker_args=("--memory", "128m", "--memory-swap", "128m"),
        needs_docker=True,
    ),
    Condition(
        name="no_network",
        label="Network off",
        category="network",
        description="Container has no network access at all (--network none).",
        docker_args=("--network", "none"),
        needs_docker=True,
    ),
    Condition(
        name="reverse_order",
        label="Reverse order",
        category="order",
        description="Tests run in exactly the reverse of the normal order.",
        env={"FLAKELAB_ORDER": "reverse"},
    ),
    Condition(
        name="shuffled_order",
        label="Shuffled order",
        category="order",
        description="Tests run in a random (seeded, reproducible) order each run.",
        env={"FLAKELAB_ORDER": "random"},
    ),
    Condition(
        name="timezone_ist",
        label="Timezone UTC+5:30",
        category="timezone",
        description="System timezone set to UTC+5:30 instead of UTC (TZ=IST-5:30).",
        env={"TZ": "IST-5:30"},
    ),
]

# What each category suggests, phrased as a hypothesis, never as proof.
HYPOTHESES = {
    "cpu": {
        "title": "Resource sensitivity (CPU / timing)",
        "explanation": "The test fails more often when CPU is scarce. It probably "
        "depends on something finishing within a fixed time.",
        "fix": "Replace fixed sleeps and hard deadlines with condition-based waits, "
        "or mock the clock. If a deadline is a real requirement, test it separately "
        "on controlled hardware.",
    },
    "memory": {
        "title": "Memory sensitivity",
        "explanation": "The test fails more often when memory is limited. It may "
        "allocate more memory than a small CI runner provides.",
        "fix": "Use smaller test data, stream instead of loading everything into "
        "memory, or document the minimum runner memory.",
    },
    "network": {
        "title": "Hidden external dependency",
        "explanation": "The test fails more often without network access, so it "
        "depends on a service outside the test.",
        "fix": "Mock or fake the external service in unit tests, and move real "
        "network checks into a separate integration-test job.",
    },
    "order": {
        "title": "Test-order dependency (shared state)",
        "explanation": "The test's result depends on which tests ran before it, "
        "so tests share state.",
        "fix": "Reset shared state in fixtures, avoid module-level mutable data, and "
        "make every test create the data it needs.",
    },
    "timezone": {
        "title": "Environment assumption (timezone)",
        "explanation": "The test fails when the machine's timezone changes, so it "
        "assumes a particular local time.",
        "fix": "Use timezone-aware datetimes (UTC) in code, and pass time zones "
        "explicitly instead of relying on the machine's setting.",
    },
}


def get_conditions(names: list[str] | None) -> list[Condition]:
    """Return the requested conditions, always including the baseline first."""
    if not names or names == ["all"]:
        return list(ALL_CONDITIONS)
    by_name = {c.name: c for c in ALL_CONDITIONS}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise ValueError(
            f"Unknown condition(s): {', '.join(unknown)}. Available: {', '.join(by_name)}"
        )
    chosen = [BASELINE] + [by_name[n] for n in names if n != "baseline"]
    return chosen
