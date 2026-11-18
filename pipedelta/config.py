"""The project's trust list, read from .pipedelta.yml.

    trusted-actions:          # actions the project has reviewed and accepts
      - docker/*
      - pypa/gh-action-pypi-publish
    trusted-hosts:            # addresses that are meant to receive data
      - pypi.org
      - "*.codecov.io"

Findings about these become low-level notes instead of blocking the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase

import yaml

CONFIG_FILE = ".pipedelta.yml"


@dataclass(frozen=True)
class Trust:
    actions: tuple[str, ...] = field(default_factory=tuple)
    hosts: tuple[str, ...] = field(default_factory=tuple)

    def trusts_action(self, action: str) -> bool:
        name = action.split("@", 1)[0].lower()
        return any(fnmatchcase(name, pattern.lower()) for pattern in self.actions)

    def trusts_host(self, host: str) -> bool:
        host = host.lower()
        return any(
            fnmatchcase(host, pattern.lower())
            or (not pattern.startswith("*") and host.endswith("." + pattern.lower()))
            for pattern in self.hosts
        )


def parse_trust(text: str | None) -> Trust:
    """Read a trust list. A missing or broken file trusts nothing."""
    if not text:
        return Trust()
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return Trust()
    if not isinstance(doc, dict):
        return Trust()

    def strings(key: str) -> tuple[str, ...]:
        value = doc.get(key) or []
        if not isinstance(value, list):
            return ()
        return tuple(str(v).strip() for v in value if str(v).strip())

    return Trust(strings("trusted-actions"), strings("trusted-hosts"))
