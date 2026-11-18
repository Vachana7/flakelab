"""Read one workflow file and list its powers.

A "power" is one thing the pipeline is able to do, for example
"can read the secret AWS_KEY" or "runs when a stranger opens a pull request".
Each power is a small record: (kind, name, where).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

# ${{ secrets.NAME }} and ${{ secrets['NAME'] }}
SECRET_RE = re.compile(
    r"secrets\.([A-Za-z_][A-Za-z0-9_]*)|secrets\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"
)
# http://host or https://host inside a shell command
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")
# Commands that talk to the network. Used to find addresses written without
# http:// ("curl evil.example") and addresses only known at run time ("curl $URL").
NET_CMD_RE = re.compile(
    r"(?:^|[\s;&|(`])(curl|wget|nc|ncat|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b([^\n;&|]*)"
)
_BARE_HOST_RE = re.compile(r"^([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?::\d+)?(?:/\S*)?$")
# Last part of a word that is a file name, not a web address (out.tar.gz, data.json).
_FILE_ENDINGS = {
    "gz",
    "tgz",
    "bz2",
    "xz",
    "zip",
    "tar",
    "json",
    "txt",
    "sh",
    "yml",
    "yaml",
    "xml",
    "log",
    "py",
    "js",
    "md",
    "html",
    "deb",
    "rpm",
    "exe",
    "whl",
    "toml",
    "cfg",
    "ini",
    "csv",
    "pem",
    "key",
    "crt",
    "out",
    "zst",
    "sig",
    "asc",
    "lock",
    "env",
    "jar",
}
# Flags whose next word is a file or a value, not the address.
_VALUE_FLAGS = {
    "-o",
    "--output",
    "-O",
    "-d",
    "--data",
    "--data-raw",
    "--data-binary",
    "-F",
    "--form",
    "-H",
    "--header",
    "-u",
    "--user",
    "-T",
    "--upload-file",
    "-X",
    "--request",
    "-A",
    "--user-agent",
    "-e",
    "--referer",
    "--cacert",
    "--cert",
    "--key",
    "-w",
    "--write-out",
    "--output-document",
    "-P",
    "--directory-prefix",
    "--retry",
    "-m",
    "--max-time",
    "--connect-timeout",
    "-b",
    "--cookie",
    "-c",
    "--cookie-jar",
    "--header=",
}
# Outsider-controlled values inside any ${{ ... }} expression, also when wrapped
# in a function such as format() or toJSON().
UNTRUSTED_RE = re.compile(
    r"\$\{\{(?:(?!\}\}).)*?\bgithub\.("
    r"event\.(issue|pull_request|comment|review|review_comment|head_commit|commits|discussion"
    r"|discussion_comment|pages|workflow_run\.(head_branch|head_commit|display_title|pull_requests))"
    r"[A-Za-z0-9_.\[\]*]*|head_ref)(?:(?!\}\}).)*\}\}"
)
# Values under those events that are numbers or commit ids, which nobody can
# use to inject a command.
_SAFE_SUFFIX_RE = re.compile(r"\.(number|id|sha|merged|draft|additions|deletions|commits)\s*\}\}$")
# ${{ toJSON(secrets) }} hands over every secret at once
ALL_SECRETS_RE = re.compile(r"toJSON\(\s*secrets\s*\)", re.IGNORECASE)
# text that is decoded and immediately run, so a reviewer cannot read what it does
_DECODE = r"(base64\s+(-d|-D|--decode)\b|xxd\s+-r\b|openssl\s+(base64|enc)\b[^\n|]*\s-d\b|gunzip\b|zcat\b)"
_RUNNER = r"(sudo\s+)?((ba|z|da|k)?sh|python[0-9.]*|perl|ruby|node|php|pwsh|powershell)\b"
HIDDEN_RE = re.compile(
    _DECODE
    + r"[^\n]*\|\s*"
    + _RUNNER
    + r"|eval\s+[\"']?\$\([^)]*"
    + _DECODE
    + r"|"
    + _RUNNER
    + r"\s+(-c\s+)?[\"']?\$\([^)]*"
    + _DECODE
    + r"|FromBase64String"
    + r"|exec\(\s*(base64\.b64decode|__import__\(['\"]base64)"
)
# Patterns seen in the 2025 and 2026 attacks.
# Reading the runner's memory, where secrets are kept (tj-actions/changed-files, 2025).
MEMORY_RE = re.compile(
    r"/proc/[^\s'\"]*/(mem|maps|environ)\b|Runner\.Worker|memdump", re.IGNORECASE
)
# Writing workflow files from inside a workflow (prt-scan, 2026): needs both a
# workflow path and a way to push it.
WORKFLOW_PATH_RE = re.compile(r"\.github/workflows")
PUSH_RE = re.compile(r"\bgit\s+push\b|\bgh\s+api\b|/contents/|createOrUpdateFileContents")
# Starting other workflows.
DISPATCH_RE = re.compile(r"\bgh\s+workflow\s+run\b|/dispatches\b|createWorkflowDispatch")
# Adding labels, which some projects use as an approval gate (prt-scan, 2026).
LABEL_RE = re.compile(r"\bgh\s+(pr|issue)\s+edit\b[^\n]*--add-label|/labels\b|addLabels")
# Deleting run logs or rewriting history to hide what happened (wfx-loot, 2026).
COVER_RE = re.compile(
    r"\bgh\s+run\s+delete\b|deleteWorkflowRun|deleteWorkflowRunLogs"
    r"|-X\s*DELETE[^\n]*/actions/runs|/actions/runs/[^\n]*(-X\s*DELETE|--method\s+DELETE)"
    r"|\bgit\s+push\b[^\n]*(--force\b|\s-f\b|\s\+\S)"
)

# a 40-character commit id means the action version cannot be swapped later
PINNED_RE = re.compile(r"@[0-9a-f]{40}$")

# Triggers that let people outside the project start the pipeline
# while it still has access to the project's secrets.
RISKY_TRIGGERS = {"pull_request_target", "workflow_run", "issue_comment"}


@dataclass(frozen=True, order=True)
class Power:
    kind: str  # trigger, permission, secret, action, network, injection, runner, hidden,
    # memory, selfmod, cover, cache
    name: str  # the specific thing, e.g. "AWS_KEY" or "contents: write"
    where: str = "workflow"  # which job it was found in


NO_LIMIT = "repository default (no limit set in the file)"
BUILT_IN_TOKEN = "GITHUB_TOKEN"

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e]")


def clean(text: object) -> str:
    """Make text taken from a workflow file safe to print.

    Job names, action names and trigger names are written by whoever made the
    change, who may be an attacker. Control characters could fake lines in a
    terminal, so they are removed, and very long names are cut.
    """
    out = _CONTROL_RE.sub(" ", str(text)).strip()
    return out if len(out) <= 100 else out[:97] + "..."


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _triggers(doc: dict[Any, Any]) -> list[str]:
    # YAML reads the bare word "on" as the boolean True, so check both keys.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(t) for t in on]
    if isinstance(on, dict):
        return [str(t) for t in on]
    return []


def _permissions(value: Any, where: str) -> list[Power]:
    if value is None:
        return []
    if isinstance(value, str):  # "write-all" or "read-all"
        return [Power("permission", clean(value), where)]
    if isinstance(value, dict):
        return [
            Power("permission", clean(f"{scope}: {level}"), where)
            for scope, level in value.items()
            if level != "none"
        ]
    return []


def _strings(node: Any) -> list[str]:
    """Every piece of text anywhere inside a YAML value."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


ALL_SECRETS = "(every secret at once)"


def _secret_names(text: str) -> list[str]:
    names = [dotted or bracket for dotted, bracket in SECRET_RE.findall(text)]
    if ALL_SECRETS_RE.search(text):
        names.append(ALL_SECRETS)
    return names


RUNTIME_ADDRESS = "(an address only known when the job runs)"


def network_hosts(run: str) -> set[str]:
    """Addresses a shell command contacts.

    Full web addresses are read directly. After curl, wget and similar
    commands, a bare host name ("curl evil.example") is also an address, and a
    target made only of variables ("curl $URL") is reported as an address that
    is only known when the job runs, so a reviewer cannot check it.
    """
    hosts = {h.lower().rstrip(".") for h in URL_RE.findall(run)}
    for _cmd, rest in NET_CMD_RE.findall(run):
        words = rest.split()
        targets: list[str] = []
        skip = False
        for word in words:
            if skip:
                skip = False
                continue
            if word in _VALUE_FLAGS:
                skip = True
                continue
            if word.startswith(("-", ">")) or word == "<":
                continue
            targets.append(word.strip("\"'"))
        literal = False
        variable = False
        for target in targets:
            if URL_RE.match(target):
                literal = True
                continue
            if "$" in target:
                # "$URL" or "${{ vars.URL }}" but not "https://x/$PATH"
                variable = True
                continue
            m = _BARE_HOST_RE.match(target)
            if m and m.group(1).rsplit(".", 1)[-1].lower() not in _FILE_ENDINGS:
                hosts.add(m.group(1).lower().rstrip("."))
                literal = True
        if variable and not literal:
            hosts.add(RUNTIME_ADDRESS)
    return hosts


def has_injection(text: str) -> bool:
    for match in UNTRUSTED_RE.finditer(text):
        if not _SAFE_SUFFIX_RE.search(match.group(0)):
            return True
    return False


def _image(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("image"), str):
        return value["image"]
    return None


def _steps_powers(steps: Any, where: str) -> set[Power]:
    powers: set[Power] = set()
    for step in _as_list(steps):
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if isinstance(uses, str):
            if uses.startswith("./"):
                powers.add(Power("local", clean(uses.rstrip("/")), where))
            else:
                powers.add(Power("action", clean(uses), where))
        texts: list[str] = []
        run = step.get("run")
        if isinstance(run, str):
            texts.append(run)
            for host in network_hosts(run):
                powers.add(Power("network", clean(host), where))
            if HIDDEN_RE.search(run):
                powers.add(Power("hidden", "decodes hidden text and runs it", where))
        with_ = step.get("with")
        # actions/github-script runs its "script" input as JavaScript, so
        # it is a shell command in all but name.
        if (
            isinstance(uses, str)
            and isinstance(with_, dict)
            and action_name(uses) == "actions/github-script"
            and isinstance(with_.get("script"), str)
        ):
            texts.append(with_["script"])
            if HIDDEN_RE.search(with_["script"]) or "eval(" in with_["script"]:
                powers.add(Power("hidden", "decodes hidden text and runs it", where))
        powers.update(_attack_patterns(texts, where))
        if isinstance(uses, str) and _uses_cache(uses, with_):
            powers.add(Power("cache", "shares a build cache with other runs", where))
        if any(has_injection(t) for t in texts):
            powers.add(
                Power("injection", "outsider-controlled text used in a shell command", where)
            )
    return powers


WRITES_WORKFLOWS = "writes workflow files"
STARTS_WORKFLOWS = "starts other workflows"
ADDS_LABELS = "adds labels to pull requests or issues"


def _attack_patterns(texts: list[str], where: str) -> set[Power]:
    """Commands seen in recent real attacks, in run: blocks and github-script."""
    powers: set[Power] = set()
    for text in texts:
        if MEMORY_RE.search(text):
            powers.add(Power("memory", "reads the runner's memory, where secrets are kept", where))
        if WORKFLOW_PATH_RE.search(text) and PUSH_RE.search(text):
            powers.add(Power("selfmod", WRITES_WORKFLOWS, where))
        if DISPATCH_RE.search(text):
            powers.add(Power("selfmod", STARTS_WORKFLOWS, where))
        if LABEL_RE.search(text):
            powers.add(Power("selfmod", ADDS_LABELS, where))
        if COVER_RE.search(text):
            powers.add(Power("cover", "deletes workflow runs or rewrites git history", where))
    return powers


def _uses_cache(uses: str, with_: Any) -> bool:
    """actions/cache, or a setup action with its built-in cache turned on."""
    name = action_name(uses)
    if name.startswith("actions/cache"):
        return True
    if isinstance(with_, dict):
        value = with_.get("cache")
        return isinstance(value, str) and value.strip() not in ("", "false")
    return False


def extract_powers(text: str) -> set[Power]:
    """Return the set of powers found in one workflow file's text."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        return set()

    powers: set[Power] = set()

    runs = doc.get("runs")
    if "jobs" not in doc and isinstance(runs, dict):
        return _action_powers(doc, runs)

    for trigger in _triggers(doc):
        powers.add(Power("trigger", clean(trigger)))

    powers.update(_permissions(doc.get("permissions"), "workflow"))
    limited_for_all_jobs = "permissions" in doc

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}

    # Secrets set at the top of the file are visible to every job.
    for s in _strings(doc.get("env")):
        for name in _secret_names(s):
            powers.add(Power("secret", name, "workflow"))

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        where = clean(job_name)
        powers.update(_permissions(job.get("permissions"), where))
        if not limited_for_all_jobs and "permissions" not in job:
            # With no limit written anywhere, the token gets whatever the
            # repository's default is, which can include write access.
            powers.add(Power("permission", NO_LIMIT, where))

        runs_on = job.get("runs-on")
        if isinstance(runs_on, dict):  # the "group / labels" form
            runs_on = runs_on.get("labels")
        labels = [label for label in _as_list(runs_on) if isinstance(label, str)]
        if any("${{" in label for label in labels):
            # "runs-on: ${{ matrix.os }}": the real labels are in the matrix.
            labels += _strings(job.get("strategy"))
        if any("self-hosted" in label for label in labels):
            powers.add(Power("runner", "self-hosted", where))

        reusable = job.get("uses")
        # A reusable workflow from another repository is outside code.
        # One that starts with "./" lives in this repository and is reviewed here.
        if isinstance(reusable, str) and not reusable.startswith("./"):
            powers.add(Power("action", clean(reusable), where))
        if job.get("secrets") == "inherit":
            powers.add(Power("secret", "(all secrets, inherited)", where))

        for s in _strings(job):
            for name in _secret_names(s):
                powers.add(Power("secret", name, where))

        powers.update(_steps_powers(job.get("steps"), where))

        services = job.get("services")
        images = [_image(job.get("container"))]
        if isinstance(services, dict):
            images += [_image(service) for service in services.values()]
        for image in images:
            if image:
                powers.add(Power("container", clean(image), where))
    return powers


def _action_powers(doc: dict[Any, Any], runs: dict[Any, Any]) -> set[Power]:
    """Powers of an action defined in this repository (an action.yml file).

    Workflows call these with "uses: ./path". Without reading them, everything
    an attacker moves into such a file would be invisible.
    """
    where = "(action file)"
    powers: set[Power] = set()
    using = str(runs.get("using", "")).lower()
    if using == "composite":
        powers.update(_steps_powers(runs.get("steps"), where))
        for s in _strings(runs.get("steps")):
            for name in _secret_names(s):
                powers.add(Power("secret", name, where))
    elif using == "docker":
        image = str(runs.get("image", ""))
        if image.startswith("docker://"):
            powers.add(Power("action", clean(image), where))
        else:
            powers.add(Power("code", clean(f"builds and runs container {image}"), where))
    elif using.startswith("node"):
        powers.add(Power("code", clean(f"runs JavaScript {runs.get('main', '')}"), where))
    return powers


def is_pinned(action: str) -> bool:
    return bool(PINNED_RE.search(action)) or action.startswith("docker://") and "@sha256:" in action


def action_name(action: str) -> str:
    """The action without its version: 'owner/tool@v1' -> 'owner/tool'."""
    return action.split("@", 1)[0].lower()


def action_owner(action: str) -> str:
    return action.split("/", 1)[0].lower()
