# PipeDelta in one page

**Your CI pipeline just changed. What can it do now that it could not do before?**

## The problem

In 2026, attackers stopped looking for weak pipelines and started **changing** them.
GhostAction (30,000+ repositories) and wfx-loot (about 8,000 repositories, last week)
used stolen tokens to push secret-stealing workflows straight to `main`. No pull
request, so no review and no PR check. A reviewer who does see a change sees ten
plausible lines of YAML.

## What PipeDelta does

It compares the pipeline before and after every pull request **and every push**, and
says in plain sentences which new powers it gained: secrets it can read, addresses it
contacts, token permissions, identity tokens (OIDC), outside code, hidden commands,
self-modification. Each finding has a concrete fix, and dangerous gains fail the check.

> In job 'security', a command now contacts collector.example.invalid. The same job
> can read secrets, so they could be sent there.

## Evidence

| | PipeDelta 0.5 | PipeDelta 0.4 | zizmor 1.32 |
|---|---|---|---|
| Real 2024 to 2026 incidents replayed (`docs/REPLAY.md`) | 9 of 9 | 6 of 9 | 2 of 9 (new high) |
| 1,659 real workflow commits, 8 projects | about 1 in 11 blocked (v0.4) | | about 1 in 3 new high |

Honest caveats: the replay cases are reconstructions written alongside the rules, and
zizmor is built for posture, not changes. PipeDelta uses zizmor as a second opinion.

## Built like production software

- Docker GitHub Action and CLI; offline demo with Docker Compose (`network_mode: none`)
- Multi-arch images on GHCR, **signed with Sigstore**, with **SLSA provenance** and an **SPDX SBOM**
- SARIF output into GitHub's Security tab; JSON for dashboards
- Holds itself to its own rules: every action pinned to a commit, least-privilege tokens,
  and PipeDelta reviews its own workflow changes and pushes

## Next

Upstream action diffs for GitHub's new lockfiles (the tj-actions pattern), then a
GitHub App that watches every push across an organisation, deployed with Helm and
monitored with Prometheus and Grafana.

github.com/Vachana7/pipedelta
