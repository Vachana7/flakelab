# PipeDelta: positioning and roadmap

As of 18 Nov 2026.

## The problem, in 2026

Every major CI/CD incident of 2026 changed or abused a pipeline file, and the two
largest never opened a pull request:

| When | Incident | What it means for a change reviewer |
|---|---|---|
| Nov 2026 | [wfx-loot](https://techaeris.com/2026/11/12/github-actions-attack-hits-1835-repos/): stolen tokens for 4,837 accounts, stealer ran in 1,835 repos, minted OIDC tokens, then "ci: cleanup" commits | Direct pushes and self-erasing commits: review pushes, not only PRs |
| Sep to Oct 2026 | [GhostAction returns](https://nhimg.org/ghostaction-returns-2026-772-repositories): fake "Github Actions Security" workflows pushed to 772, then 30,000+ repos | The "secret plus new address" pattern, delivered by push |
| May 2026 | [Mini Shai-Hulud](https://labs.cloudsecurityalliance.org/research/csa-research-note-mini-shai-hulud-npm-supply-chain-20260516/): `pull_request_target` abuse, OIDC token swapped for npm trusted publishing, 172 packages with valid SLSA provenance | OIDC reachable from outsider triggers is a top-tier power; provenance is not safety |
| Mar to Apr 2026 | [prt-scan](https://labs.cloudsecurityalliance.org/research/csa-research-note-github-actions-prt-scan-supply-chain-2026/): 500+ PRs, token used to add workflows and self-apply approval labels | Workflow-writes-workflow and label gates are powers |
| Mar 2025 | [tj-actions/changed-files](https://www.wiz.io/blog/github-action-tj-actions-changed-files-supply-chain-attack-cve-2025-30066): all tags repointed to a memory dumper | The risk was an upstream action changing: diff upstream code |
| Dec 2024 | [Ultralytics](https://blog.pypi.org/posts/2024-12-11-ultralytics-attack-analysis/): injection, then cache poisoning into the release job | Caches shared with untrusted runs are a power |

GitHub's [2026 security roadmap](https://github.blog/news-insights/product-news/whats-coming-to-our-github-actions-2026-security-roadmap/)
adds workflow lockfiles ([preview since 14 Oct 2026](https://github.blog/changelog/2026-10-14-github-actions-workflow-lockfiles-in-public-preview/)),
an egress firewall, scoped secrets and trigger policies. GitHub itself notes that
locking "does not determine whether the dependency itself is safe".

## Where PipeDelta fits

| Tool | Answers |
|---|---|
| zizmor, poutine, actionlint, CodeQL | Is this workflow file weak right now? |
| OpenSSF Scorecard | How healthy is this repository's posture? |
| Harden-Runner, GitHub egress firewall | What does the job actually contact at run time? |
| GitHub lockfiles | Is the action exactly the commit we pinned? |
| **PipeDelta** | **What can the pipeline do now that it could not before, and should a human worry?** |

PipeDelta runs zizmor as a second opinion and keeps only its new findings. The
pitch is "zizmor for posture, PipeDelta for changes", not "PipeDelta beats zizmor".

## Roadmap

1. **Proof (done in 0.5).** 2026 attack rules, push review, incident replay
   benchmark, SARIF output, signed multi-arch images with SBOM and SLSA provenance.
2. **Upstream review.** When a `uses:` commit, tag or `actions.lock` entry changes,
   fetch the action at both commits and report its new powers. Hand-label the 155
   commits blocked in the history test and publish precision.
3. **Org monitor.** A GitHub App that reviews every push touching workflows across an
   organisation, from outside the repository (so a push cannot switch it off).
   FastAPI webhook service, Postgres findings, Helm chart tested on kind, Prometheus
   metrics and a Grafana dashboard, Slack or issue alerts.
4. **Reach.** Scale run over workflow changes in 500+ public repositories with private
   disclosure, a public write-up, reading egress logs (GitHub firewall monitor mode or
   Harden-Runner) to compare declared and observed powers, and a GitLab CI adapter.

Not planned: an own runtime firewall, a hosted multi-tenant service, a general SAST
engine. Each is crowded or being shipped by GitHub.

## How we will know it works

- Replay benchmark grows with each new public incident; cases are reproducible.
- Precision on real history is published, even when it is unflattering.
- Five repositories outside the author's own run it.
